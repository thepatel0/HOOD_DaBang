"""
HOOD DaBang — autonomous orchestrator (the "wake up, research, trade, count" loop).

Ties the pieces into one runnable, repeatable cycle:
  wake -> research (real data -> MarketStates) -> decision tree (Conviction Gate
  + risk gate + deployment cap) -> place buy/sell via the wired adapter -> manage
  open positions (stops/targets) -> count realized + unrealized P&L.

It is transport-agnostic: with a sim transport it PAPER-trades (free, safe); with
a real Robinhood transport it LIVE-trades within every guardrail (deployment cap,
per-trade cap, conviction floor, review-before-place, session hours). It runs only
while the control plane is armed, and re-checks killswitches every cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..strategies.base import MarketState
from ..research.runner import ResearchRunner
from .autonomous_loop import TradingLoop, CycleResult


@dataclass
class ProfitReport:
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    trades_closed: int
    open_positions: int
    equity: float

    def line(self) -> str:
        return (f"P&L realized ${self.realized_pnl:+.2f} | unrealized "
                f"${self.unrealized_pnl:+.2f} | total ${self.total_pnl:+.2f} | "
                f"{self.trades_closed} closed, {self.open_positions} open | "
                f"equity ${self.equity:,.2f}")


class AutonomousOrchestrator:
    def __init__(self, controller, journal, bar_feed, watchlist: List[str], *,
                 is_armed: Callable[[], bool], heartbeat: Callable[[], bool] = None,
                 regime_classifier=None, allow_extended: bool = False,
                 now_fn: Callable[[], object] = None, last_price: Dict[str, float] = None):
        self.controller = controller
        self.journal = journal
        self.bar_feed = bar_feed
        self.watchlist = watchlist
        self._now = now_fn or (lambda: None)
        self.runner = ResearchRunner(bar_feed, controller,
                                     regime_classifier=regime_classifier)
        self.loop = TradingLoop(
            controller, is_armed=is_armed,
            state_provider=self._state_provider,
            heartbeat=heartbeat or (lambda: True), now_fn=now_fn,
            allow_extended=allow_extended)
        self._last_price = last_price or {}

    # research step: real data -> MarketStates for the watchlist
    def _now_et_iso(self) -> str:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            dt = self._now() or datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            dt = self._now() or datetime.now()
        return dt.isoformat()

    def _state_provider(self, now_et: str) -> Dict[str, MarketState]:
        now_et = now_et or self._now_et_iso()   # always stamp a real timestamp
        regime = self.runner.detect_regime()
        states: Dict[str, MarketState] = {}
        for t in self.watchlist:
            ms = self.runner.build_state(t, now_et, regime)
            if ms is not None:
                states[t] = ms
                self._last_price[t] = ms.quote
        return states

    def run(self, *, max_cycles: int = 1, sleep_s: float = 0.0,
            sleep_fn: Callable[[float], None] = None) -> List[CycleResult]:
        kw = {"sleep_fn": sleep_fn} if sleep_fn else {}
        return self.loop.run(max_cycles=max_cycles, sleep_s=sleep_s, **kw)

    # profit counting: realized (closed trades) + unrealized (open mark-to-market)
    def profit_report(self) -> ProfitReport:
        closed = self.journal.closed_trades()
        realized = sum(t.get("pnl_dollars", 0.0) for t in closed)
        unrealized = 0.0
        for ticker, ot in self.controller.open.items():
            last = self._last_price.get(ticker, ot.pos.entry_price)
            if ot.pos.side == "long":
                unrealized += (last - ot.pos.entry_price) * ot.pos.shares
            else:
                unrealized += (ot.pos.entry_price - last) * ot.pos.shares
        return ProfitReport(
            realized_pnl=round(realized, 2), unrealized_pnl=round(unrealized, 2),
            total_pnl=round(realized + unrealized, 2), trades_closed=len(closed),
            open_positions=len(self.controller.open),
            equity=round(self.controller.state.equity, 2))
