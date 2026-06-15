"""
HOOD DaBang — Robinhood Agentic MCP client (Brief §34, failure mode #6).

A thin, TYPED wrapper around the broker MCP at
https://agent.robinhood.com/mcp/trading. Every call validates its params and its
response; a response missing required fields or with insane types is treated as
fabricated and raises (fail-closed) rather than feeding garbage downstream.

The transport is pluggable:
  - MockTransport     — deterministic, for tests and the paper simulator.
  - HttpMCPTransport  — speaks MCP JSON-RPC over HTTP (needs httpx); the ACTUAL
                        tool names/params must be confirmed via discover() before
                        live trading (§34 — verify, never assume).

This file does NOT hardcode that the MCP tools are named a certain way: the
wrapper maps logical operations to tool names supplied at construction, so when
the operator runs discovery we bind to the real surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


class MCPError(RuntimeError):
    pass


class MCPSchemaError(MCPError):
    """Response/params failed validation — likely a schema drift or hallucination."""


# --------------------------------------------------------------------------- #
# Transport protocol                                                           #
# --------------------------------------------------------------------------- #
class MCPTransport(Protocol):
    def call(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]: ...
    def list_tools(self) -> List[str]: ...


# Default logical->tool name map (placeholders; rebind after discovery, §34).
DEFAULT_TOOL_MAP = {
    "get_account": "get_account_info",
    "get_buying_power": "get_buying_power",
    "get_positions": "get_positions",
    "get_quote": "get_quote",
    "preview_order": "preview_order",
    "place_order": "place_order",
    "place_stop_order": "place_stop_order",
    "cancel_order": "cancel_order",
    "get_order_status": "get_order_status",
}


# --------------------------------------------------------------------------- #
# Typed response models                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Account:
    cash: float
    equity: float
    buying_power: float


@dataclass
class BrokerPosition:
    ticker: str
    shares: int
    avg_price: float


@dataclass
class Quote:
    ticker: str
    bid: float
    ask: float
    last: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2 if self.bid and self.ask else self.last

    @property
    def spread_pct(self) -> float:
        m = self.mid
        return (self.ask - self.bid) / m if m else 1.0


@dataclass
class OrderResult:
    order_id: str
    status: str            # "accepted" | "filled" | "partial" | "rejected" | "cancelled"
    filled_shares: int
    avg_fill_price: float


def _req(d: Dict[str, Any], *keys) -> None:
    for k in keys:
        if k not in d or d[k] is None:
            raise MCPSchemaError(f"response missing required field {k!r}: {d}")


def _num(d: Dict[str, Any], k: str) -> float:
    v = d.get(k)
    if not isinstance(v, (int, float)):
        raise MCPSchemaError(f"field {k!r} not numeric: {v!r}")
    return float(v)


class RobinhoodMCPClient:
    def __init__(self, transport: MCPTransport,
                 tool_map: Optional[Dict[str, str]] = None):
        self.t = transport
        self.tools = {**DEFAULT_TOOL_MAP, **(tool_map or {})}

    # ----- discovery (§34) ----------------------------------------------- #
    def discover(self) -> List[str]:
        return self.t.list_tools()

    def validate_tool_map(self) -> List[str]:
        """Return logical ops whose mapped tool is NOT present on the server.
        A non-empty result means we'd send calls to non-existent tools -> the
        system must halt rather than trade (failure mode #6)."""
        available = set(self.t.list_tools())
        return [op for op, name in self.tools.items() if name not in available]

    # ----- read ops ------------------------------------------------------ #
    def get_account(self) -> Account:
        r = self.t.call(self.tools["get_account"], {})
        _req(r, "cash", "equity", "buying_power")
        return Account(_num(r, "cash"), _num(r, "equity"), _num(r, "buying_power"))

    def get_positions(self) -> List[BrokerPosition]:
        r = self.t.call(self.tools["get_positions"], {})
        out = []
        for p in r.get("positions", []):
            _req(p, "ticker", "shares", "avg_price")
            out.append(BrokerPosition(p["ticker"], int(p["shares"]), _num(p, "avg_price")))
        return out

    def get_quote(self, ticker: str) -> Quote:
        r = self.t.call(self.tools["get_quote"], {"ticker": ticker})
        _req(r, "bid", "ask", "last")
        return Quote(ticker, _num(r, "bid"), _num(r, "ask"), _num(r, "last"))

    # ----- write ops (marketable limit only; never market) --------------- #
    def preview_order(self, ticker: str, side: str, shares: int,
                      limit_price: float, client_order_id: str) -> Dict[str, Any]:
        self._validate_order(ticker, side, shares, limit_price)
        return self.t.call(self.tools["preview_order"], {
            "ticker": ticker, "side": side, "shares": shares,
            "type": "limit", "limit_price": limit_price,
            "client_order_id": client_order_id})

    def place_order(self, ticker: str, side: str, shares: int,
                    limit_price: float, client_order_id: str) -> OrderResult:
        self._validate_order(ticker, side, shares, limit_price)
        r = self.t.call(self.tools["place_order"], {
            "ticker": ticker, "side": side, "shares": shares,
            "type": "limit", "limit_price": limit_price,
            "client_order_id": client_order_id})
        return self._parse_order(r)

    def place_stop_order(self, ticker: str, side: str, shares: int,
                         stop_price: float, client_order_id: str) -> OrderResult:
        """Protective stop (Brief §30.3). `side` is the EXIT side: a long
        position protects with a 'sell' stop, a short with a 'buy' stop."""
        self._validate_order(ticker, side, shares, stop_price)
        r = self.t.call(self.tools["place_stop_order"], {
            "ticker": ticker, "side": side, "shares": shares,
            "type": "stop", "stop_price": stop_price,
            "client_order_id": client_order_id})
        return self._parse_order(r)

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return self.t.call(self.tools["cancel_order"], {"order_id": order_id})

    def get_order_status(self, order_id: str) -> OrderResult:
        r = self.t.call(self.tools["get_order_status"], {"order_id": order_id})
        return self._parse_order(r)

    # ----- internals ----------------------------------------------------- #
    @staticmethod
    def _validate_order(ticker, side, shares, limit_price) -> None:
        if side not in ("buy", "sell"):
            raise MCPSchemaError(f"side must be buy/sell, got {side!r}")
        if not isinstance(shares, int) or shares <= 0:
            raise MCPSchemaError(f"shares must be positive int, got {shares!r}")
        if not isinstance(limit_price, (int, float)) or limit_price <= 0:
            raise MCPSchemaError(f"limit_price must be positive, got {limit_price!r}")

    @staticmethod
    def _parse_order(r: Dict[str, Any]) -> OrderResult:
        _req(r, "order_id", "status")
        filled = int(r.get("filled_shares", 0) or 0)
        avg = float(r.get("avg_fill_price", 0) or 0)
        return OrderResult(str(r["order_id"]), str(r["status"]), filled, avg)


# --------------------------------------------------------------------------- #
# Mock transport for tests / paper sim                                         #
# --------------------------------------------------------------------------- #
class MockTransport:
    def __init__(self, responses: Optional[Dict[str, Any]] = None,
                 tools: Optional[List[str]] = None):
        self.responses = responses or {}
        self._tools = tools or list(DEFAULT_TOOL_MAP.values())
        self.calls: List[Dict[str, Any]] = []

    def list_tools(self) -> List[str]:
        return list(self._tools)

    def call(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append({"tool": tool, "params": params})
        resp = self.responses.get(tool)
        if callable(resp):
            return resp(params)
        if resp is None:
            raise MCPError(f"MockTransport has no canned response for {tool!r}")
        return resp
