"""
HOOD DaBang — execution handler (Brief §26.6, §30.3).

OrderEvent -> preview -> place (marketable limit) -> verify fill -> place
protective stop within a 2s deadline (else FLATTEN) -> return result. Idempotent
by client_order_id. Refuses to place without a conviction verdict above floor AND
a stored thesis (killswitches #25/#26). Sizes the stop to the ACTUAL filled
quantity (partial fills handled).

The SAME handler runs in paper and live — only the MCP transport behind the
client differs (parity principle). The paper simulator is just this handler over
a MockTransport that models fills.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from .mcp_client import RobinhoodMCPClient, OrderResult, MCPError


@dataclass
class OrderRequest:
    ticker: str
    side: str                       # entry side: "buy" (long) | "sell" (short)
    shares: int
    limit_price: float
    stop_price: float
    client_order_id: str
    conviction_score: Optional[float] = None
    thesis_id: Optional[str] = None
    has_thesis: bool = False

    @property
    def exit_side(self) -> str:
        return "sell" if self.side == "buy" else "buy"


@dataclass
class ExecutionResult:
    accepted: bool
    reason: str
    order_id: Optional[str] = None
    filled_shares: int = 0
    avg_fill_price: float = 0.0
    stop_order_id: Optional[str] = None
    flattened: bool = False         # True if we closed an unhedged fill
    kill: Optional[str] = None      # set if a killswitch should fire


class ExecutionHandler:
    def __init__(self, client: RobinhoodMCPClient, cfg: dict,
                 clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.cfg = cfg
        self.execution_floor = cfg["conviction"]["execution_floor"]
        self.stop_deadline_s = cfg["latency"]["stop_confirm_deadline_s"]
        self.clock = clock
        self._seen: Dict[str, ExecutionResult] = {}   # idempotency cache

    def submit(self, req: OrderRequest) -> ExecutionResult:
        # ---- idempotency (Brief §26.6) ---------------------------------- #
        if req.client_order_id in self._seen:
            return self._seen[req.client_order_id]

        # ---- pre-trade hard gates --------------------------------------- #
        if req.conviction_score is None or req.conviction_score < self.execution_floor:
            return self._record(req, ExecutionResult(
                False, "conviction_bypass_blocked", kill="conviction_bypass"))
        if not req.has_thesis or not req.thesis_id:
            return self._record(req, ExecutionResult(
                False, "thesis_less_blocked", kill="thesis_less_trade"))
        if req.shares <= 0 or req.limit_price <= 0:
            return self._record(req, ExecutionResult(False, "invalid_order_params"))

        # ---- place entry (marketable limit, never market) --------------- #
        try:
            entry = self.client.place_order(
                req.ticker, req.side, req.shares, req.limit_price, req.client_order_id)
        except MCPError as e:
            return self._record(req, ExecutionResult(False, f"place_failed:{e}"))

        if entry.status == "rejected":
            return self._record(req, ExecutionResult(False, "entry_rejected",
                                                     order_id=entry.order_id))

        filled = entry.filled_shares
        if filled <= 0:
            # nothing filled — cancel the working order, no exposure, no stop needed
            try:
                self.client.cancel_order(entry.order_id)
            except MCPError:
                pass
            return self._record(req, ExecutionResult(
                False, "unfilled_cancelled", order_id=entry.order_id))

        # ---- atomic stop within the deadline (Brief §30.3) -------------- #
        t0 = self.clock()
        stop_id = None
        try:
            stop = self.client.place_stop_order(
                req.ticker, req.exit_side, filled, req.stop_price,
                req.client_order_id + "-stop")
            stop_id = stop.order_id
            elapsed = self.clock() - t0
            if stop.status == "rejected" or elapsed > self.stop_deadline_s:
                return self._flatten(req, entry, filled,
                                     reason=("stop_rejected" if stop.status == "rejected"
                                             else "stop_deadline_exceeded"))
        except MCPError as e:
            return self._flatten(req, entry, filled, reason=f"stop_error:{e}")

        # success: position is protected, sized to the ACTUAL fill
        res = ExecutionResult(
            True, "filled_and_protected", order_id=entry.order_id,
            filled_shares=filled, avg_fill_price=entry.avg_fill_price,
            stop_order_id=stop_id)
        return self._record(req, res)

    # ----- flatten an unhedged fill (killswitch #27) --------------------- #
    def _flatten(self, req: OrderRequest, entry: OrderResult, filled: int,
                 reason: str) -> ExecutionResult:
        try:
            self.client.place_order(
                req.ticker, req.exit_side, filled, req.limit_price,
                req.client_order_id + "-flat")
        except MCPError:
            pass  # best effort; the kill flag forces operator attention regardless
        return self._record(req, ExecutionResult(
            False, f"flattened:{reason}", order_id=entry.order_id,
            filled_shares=0, flattened=True, kill="unhedged_position"))

    def _record(self, req: OrderRequest, res: ExecutionResult) -> ExecutionResult:
        self._seen[req.client_order_id] = res
        return res
