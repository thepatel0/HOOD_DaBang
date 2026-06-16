"""
HOOD DaBang — risk gate (Brief 13, 26.4, 30.2, 30.4).

Every OrderEvent passes through `RiskGate.check` before execution. No LLM agent
can override it; only the operator via MANUAL_OVERRIDE.flag (+24h cooldown).
Fail-closed: on missing/contradictory data the order is REJECTED, never passed.

Returns ALL violated caps (not just the first) so each cap is independently
auditable and testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OrderProposal:
    ticker: str
    side: str                 # "long" | "short"
    entry_price: float
    stop_price: float
    shares: int
    spread_pct: float         # (ask-bid)/price
    strategy: str
    # freshness (Brief 30.4) — ages of the inputs the plan relied on
    quote_age_ms: int = 0
    last_bar_age_s: int = 0
    has_thesis: bool = True   # Brief: thesis-less trade is illegal (killswitch #26)
    conviction_score: Optional[float] = None  # must clear execution floor
    authorized_risk_pct: Optional[float] = None  # per-trade cap set by the
        # AdaptiveRiskGovernor; None => fall back to the brief's per_trade cap.
        # The gate ALSO enforces an immutable absolute ceiling no governor can pass.


@dataclass
class AccountState:
    equity: float                       # current account equity
    effective_capital: float            # capital-ramp amount (Brief 30.2)
    session_start_equity: float
    day_pnl: float                      # realized+unrealized today
    open_positions: int
    gross_exposure: float               # sum |position notional| currently open
    day_number: int = 1                 # live day counter (ramp/concurrency)
    manual_override: bool = False       # MANUAL_OVERRIDE.flag present
    # Deployment cap (NEXT_STEPS P3): total deployed notional must not exceed
    # deployment_cap_usd unless the operator passcode set deployment_cap_override.
    deployment_cap_usd: float = 500.0
    deployment_cap_override: bool = False


@dataclass
class RiskVerdict:
    approved: bool
    violations: List[str] = field(default_factory=list)
    risk_dollars: float = 0.0
    notional: float = 0.0
    reason: str = ""


class RiskGate:
    def __init__(self, cfg: dict):
        self.r = cfg["risk"]
        self.cfg = cfg

    def _max_concurrent(self, day_number: int) -> int:
        if day_number <= self.cfg["operation"]["intraday_only_days"]:
            return self.r["max_concurrent_positions_days_1_30"]
        return self.r["max_concurrent_positions_after"]

    def check(self, o: OrderProposal, acct: AccountState,
              freshness_tol: Optional[dict] = None) -> RiskVerdict:
        v: List[str] = []

        # ---- fail-closed structural checks ---------------------------------
        if o.shares <= 0:
            v.append("non_positive_shares")
        if o.entry_price <= 0 or o.stop_price <= 0:
            v.append("non_positive_price")
        if not o.has_thesis:
            v.append("thesis_less_trade_forbidden")            # killswitch #26
        if o.conviction_score is None:
            v.append("missing_conviction_verdict")             # killswitch #25
        elif o.conviction_score < self.cfg["conviction"]["execution_floor"]:
            v.append("below_execution_floor")

        # stop must be on the correct side of entry
        if o.side == "long" and o.stop_price >= o.entry_price:
            v.append("long_stop_not_below_entry")
        if o.side == "short" and o.stop_price <= o.entry_price:
            v.append("short_stop_not_above_entry")

        # If structurally broken, stop here — sizing math would be meaningless.
        if v:
            return RiskVerdict(False, v, reason="structural_reject")

        per_share_risk = abs(o.entry_price - o.stop_price)
        risk_dollars = per_share_risk * o.shares
        notional = o.entry_price * o.shares

        # ---- per-trade caps (Brief 13 + adaptive governor) -----------------
        equity = acct.effective_capital  # sizing uses ramp-limited capital
        # IMMUTABLE ceiling: the absolute max the adaptive governor may authorize.
        absolute_max_pct = self.cfg.get("adaptive_risk", {}).get(
            "absolute_max_pct", self.r["per_trade_risk_pct"])
        # The cap for THIS trade: what the governor authorized, but never above
        # the immutable ceiling (a governor bug can't escalate risk past it).
        authorized = o.authorized_risk_pct
        if authorized is None:
            authorized = self.r["per_trade_risk_pct"]
        if authorized > absolute_max_pct + 1e-9:
            v.append("authorized_risk_exceeds_absolute_ceiling")
            authorized = absolute_max_pct
        max_risk = authorized * equity
        if risk_dollars > max_risk + 1e-9:
            v.append("per_trade_risk_exceeds_cap")
        if notional > self.r["max_position_pct"] * equity + 1e-9:
            v.append("position_exceeds_30pct")
        if o.spread_pct > self.r["spread_reject_pct"]:
            v.append("spread_too_wide")

        # ---- daily caps ----------------------------------------------------
        loss_limit = -self.r["daily_loss_limit_pct"] * acct.session_start_equity
        if acct.day_pnl <= loss_limit:
            v.append("daily_loss_limit_hit")                   # killswitch #1
        if acct.open_positions >= self._max_concurrent(acct.day_number):
            v.append("concurrency_cap_reached")
        if acct.gross_exposure + notional > self.r["total_exposure_cap_pct"] * equity + 1e-9:
            v.append("total_exposure_cap_exceeded")

        # ---- deployment cap (NEXT_STEPS P3): hard $-cap on total deployed ----
        # capital. Overridable ONLY by the operator passcode (sets
        # deployment_cap_override); never by any agent.
        if not acct.deployment_cap_override:
            if acct.gross_exposure + notional > acct.deployment_cap_usd + 1e-9:
                v.append("deployment_cap_exceeded")

        # ---- account-level halts -------------------------------------------
        if acct.equity <= self.r["catastrophic_halt_equity_usd"]:
            v.append("catastrophic_halt")                      # killswitch #3

        # ---- freshness contract (Brief 30.4) -------------------------------
        if freshness_tol:
            if o.quote_age_ms > freshness_tol.get("quote_age_ms", 1e12):
                v.append("stale_quote")
            if o.last_bar_age_s > freshness_tol.get("last_bar_age_s", 1e12):
                v.append("stale_bar")

        # ---- operator override (Brief 13): only relaxes *soft* caps, never
        # the catastrophic halt or a thesis-less / conviction-less trade ------
        if acct.manual_override:
            HARD = {"thesis_less_trade_forbidden", "missing_conviction_verdict",
                    "catastrophic_halt", "authorized_risk_exceeds_absolute_ceiling",
                    "deployment_cap_exceeded"}  # cap lifts only via passcode override
            v = [x for x in v if x in HARD]

        approved = len(v) == 0
        return RiskVerdict(
            approved=approved,
            violations=v,
            risk_dollars=risk_dollars,
            notional=notional,
            reason="approved" if approved else "rejected:" + ",".join(v),
        )

    @staticmethod
    def shares_for_risk(entry: float, stop: float, max_risk_dollars: float) -> int:
        """Whole-share sizing (Brief 10/13): floor(max_risk / per-share-risk)."""
        per_share = abs(entry - stop)
        if per_share <= 0:
            return 0
        return int(math.floor(max_risk_dollars / per_share))
