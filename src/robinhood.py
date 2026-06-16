"""
HOOD DaBang — real Robinhood Agentic adapter (NEXT_STEPS Priority 1).

Speaks the ACTUAL Robinhood Agentic MCP tool surface, but exposes the SAME method
interface as the abstract RobinhoodMCPClient so ExecutionHandler / reconciliation
work unchanged. Key real-surface facts (verified from the live connector):

  - account_number is required on writes; orders ONLY work on an agentic_allowed
    account (the operator's is 581853207, a cash account).
  - There is NO separate stop tool: a protective stop is place_equity_order with
    type=stop_market (exit side, stop_price, gtc).
  - review_equity_order is a SAFE simulation — call it before every place
    (mandatory pre-trade preview); block on any order_checks alert.
  - place_equity_order takes market_hours (regular_hours default) + ref_id
    (UUID idempotency; we reuse client_order_id).

Transport is the abstract MCPTransport (.call/.list_tools) — the live
HttpMCPTransport or a test fake. Real responses are wrapped {"data":..,"guide":..};
parsing tolerates both wrapped and unwrapped.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .mcp_client import (Account, BrokerPosition, Quote, OrderResult, MCPError,
                         MCPSchemaError, MCPTransport)
from .ops import market_hours as mh

REAL_TOOLS = {
    "get_accounts", "get_portfolio", "get_equity_positions", "get_equity_quotes",
    "get_equity_tradability", "get_equity_historicals", "get_equity_orders",
    "review_equity_order", "place_equity_order", "cancel_equity_order", "search",
}

# RH order state -> our internal status
_STATE_MAP = {
    "filled": "filled", "partially_filled": "partial", "confirmed": "accepted",
    "queued": "accepted", "new": "accepted", "unconfirmed": "accepted",
    "cancelled": "cancelled", "rejected": "rejected", "failed": "rejected",
    "voided": "rejected",
}


def _unwrap(r: Dict[str, Any]) -> Dict[str, Any]:
    return r.get("data", r) if isinstance(r, dict) else {}


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class RobinhoodAgenticAdapter:
    def __init__(self, transport: MCPTransport, account_number: str,
                 *, audit=None, default_market_hours: str = "regular_hours"):
        self.t = transport
        self.account_number = account_number
        self.audit = audit
        self.default_market_hours = default_market_hours

    # ----- §34 discovery -------------------------------------------------- #
    def discover(self) -> List[str]:
        return self.t.list_tools()

    def validate_tool_map(self) -> List[str]:
        available = set(self.t.list_tools())
        return [name for name in REAL_TOOLS if name not in available]

    def assert_agentic_account(self) -> None:
        """Halt unless the configured account is agentic_allowed AND cash (no
        margin) — the legal/safety precondition for every live session."""
        r = _unwrap(self.t.call("get_accounts", {}))
        accts = r.get("accounts", [])
        rec = next((a for a in accts if a.get("account_number") == self.account_number), None)
        if rec is None:
            raise MCPError(f"account {self.account_number} not found")
        if not rec.get("agentic_allowed"):
            raise MCPError(f"account {self.account_number} is not agentic_allowed")
        if rec.get("type") != "cash":
            raise MCPError(f"account {self.account_number} is not a cash account "
                           f"(margin guard) — got {rec.get('type')!r}")

    # ----- reads ---------------------------------------------------------- #
    def get_account(self) -> Account:
        p = _unwrap(self.t.call("get_portfolio", {"account_number": self.account_number}))
        cash = _num(p.get("cash"))
        equity = _num(p.get("equity_value")) + cash
        bp = p.get("buying_power", {})
        buying_power = _num(bp.get("buying_power") if isinstance(bp, dict) else bp)
        return Account(cash=cash, equity=_num(p.get("total_value"), equity),
                       buying_power=buying_power)

    def get_positions(self) -> List[BrokerPosition]:
        r = _unwrap(self.t.call("get_equity_positions",
                                {"account_number": self.account_number}))
        out = []
        for pos in r.get("positions", r.get("results", [])):
            sym = pos.get("symbol") or pos.get("ticker")
            qty = _num(pos.get("quantity") or pos.get("shares"))
            avg = _num(pos.get("average_cost") or pos.get("avg_price"))
            if sym and qty:
                out.append(BrokerPosition(sym, int(qty), avg))
        return out

    def get_quote(self, ticker: str) -> Quote:
        r = _unwrap(self.t.call("get_equity_quotes", {"symbols": [ticker]}))
        results = r.get("results", [])
        if not results:
            raise MCPSchemaError(f"no quote for {ticker}")
        q = results[0].get("quote", results[0])
        bid, ask = _num(q.get("bid_price")), _num(q.get("ask_price"))
        last = _num(q.get("last_trade_price") or q.get("last_non_reg_trade_price"))
        return Quote(ticker, bid, ask, last)

    # ----- writes (review-before-place + stop-as-order) ------------------ #
    def _review(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return _unwrap(self.t.call("review_equity_order", params))

    def place_order(self, ticker: str, side: str, shares: int, limit_price: float,
                    client_order_id: str, *, market_hours: Optional[str] = None,
                    skip_review: bool = False) -> OrderResult:
        mhrs = market_hours or self.default_market_hours
        base = {"account_number": self.account_number, "symbol": ticker, "side": side,
                "type": "limit", "quantity": str(shares),
                "limit_price": f"{limit_price:.2f}", "time_in_force": "gfd",
                "market_hours": mhrs}

        # mandatory pre-trade preview (block on alerts)
        if not skip_review:
            review = self._review(base)
            self._audit("REVIEWED", ticker, side, "limit", shares, limit_price,
                        client_order_id, review_result=review)
            checks = review.get("order_checks", {}) if isinstance(review, dict) else {}
            blocking = {k: val for k, val in (checks or {}).items()
                        if val not in (None, False, "", [], {})}
            if blocking:
                self._audit("REJECTED", ticker, side, "limit", shares, limit_price,
                            client_order_id, outcome={"preview_blocked": blocking})
                return OrderResult(order_id="", status="rejected", filled_shares=0,
                                   avg_fill_price=0.0)

        result = _unwrap(self.t.call("place_equity_order",
                                     {**base, "ref_id": client_order_id}))
        res = self._parse_order(result)
        self._audit("PLACED", ticker, side, "limit", shares, limit_price,
                    client_order_id, outcome=result)
        return res

    def place_stop_order(self, ticker: str, side: str, shares: int, stop_price: float,
                         client_order_id: str, *,
                         market_hours: Optional[str] = None) -> OrderResult:
        """Protective stop = place_equity_order type=stop_market on the exit side."""
        mhrs = market_hours or self.default_market_hours
        params = {"account_number": self.account_number, "symbol": ticker,
                  "side": side, "type": "stop_market", "quantity": str(shares),
                  "stop_price": f"{stop_price:.2f}", "time_in_force": "gtc",
                  "market_hours": mhrs, "ref_id": client_order_id}
        result = _unwrap(self.t.call("place_equity_order", params))
        res = self._parse_order(result)
        self._audit("STOP_PLACED", ticker, side, "stop_market", shares, stop_price,
                    client_order_id, outcome=result)
        return res

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        out = self.t.call("cancel_equity_order", {"account_number": self.account_number,
                                                  "order_id": order_id})
        self._audit("CANCELLED", "", "", "", 0, 0, "", outcome=out)
        return out

    def get_order_status(self, order_id: str) -> OrderResult:
        r = _unwrap(self.t.call("get_equity_orders",
                                {"account_number": self.account_number,
                                 "order_id": order_id}))
        orders = r.get("orders", [])
        return self._parse_order(orders[0] if orders else {})

    # ----- helpers -------------------------------------------------------- #
    def _parse_order(self, r: Dict[str, Any]) -> OrderResult:
        if not r:
            return OrderResult(order_id="", status="rejected", filled_shares=0,
                               avg_fill_price=0.0)
        oid = str(r.get("id") or r.get("order_id") or "")
        state = str(r.get("state") or r.get("status") or "accepted").lower()
        status = _STATE_MAP.get(state, "accepted")
        filled = int(_num(r.get("cumulative_quantity") or r.get("filled_shares") or 0))
        avg = _num(r.get("average_price") or r.get("avg_fill_price") or 0)
        return OrderResult(order_id=oid, status=status, filled_shares=filled,
                           avg_fill_price=avg)

    def _audit(self, event, ticker, side, order_type, qty, price, ref, **kw):
        if self.audit is not None:
            self.audit.record(event, account_number=self.account_number, symbol=ticker,
                              side=side, order_type=order_type, quantity=float(qty),
                              price=float(price), ref_id=ref, **kw)
