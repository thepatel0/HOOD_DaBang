"""
HOOD DaBang — killswitches (Brief 14 + 30.7).

Evaluated every tick. Each fired condition produces a Halt with a scope and a
human reason; all are loud and journal-written by the controller. KillEvent
jumps the bus.

This module implements the conditions evaluable purely from system state
(the rest — MCP failure, feed staleness, P&L velocity — get wired when their
data sources exist, and register here through the same interface).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional


class HaltScope(Enum):
    NONE = "none"
    PAUSE_TICKER = "pause_ticker"
    PAUSE_NEW_ORDERS = "pause_new_orders"
    HALT_SESSION = "halt_session"
    HALT_UNTIL_RESUME = "halt_until_operator_resume"
    HALT_INDEFINITE = "halt_indefinite"
    BUDGET_PAUSE = "budget_pause_llm_only"  # Tier 0 keeps running


@dataclass
class KillswitchState:
    # account / pnl
    day_pnl: float = 0.0
    session_start_equity: float = 1500.0
    equity: float = 1500.0
    ath_equity: float = 1500.0
    catastrophic_floor: float = 1050.0
    consecutive_losses: int = 0
    consecutive_order_rejections: int = 0
    # flags on disk
    halt_flag: bool = False
    # budget
    llm_daily_spent: float = 0.0
    llm_daily_budget: float = 5.0
    llm_monthly_spent: float = 0.0
    llm_monthly_budget: float = 60.0
    # live feeds (Brief §13/§17)
    mcp_heartbeat_age_s: float = 0.0            # #4
    data_feed_stale_age_s: float = 0.0          # #6
    has_open_position: bool = False
    quote_spike_unexplained: bool = False       # #11 >10% in 5s w/o vol+news
    pnl_velocity_anomaly: bool = False          # #13
    order_rate_excessive: bool = False          # #17 amplification
    # integrity / safety
    reconciliation_desync: bool = False
    self_test_failed: bool = False
    conviction_bypass_detected: bool = False   # order reached exec w/o ConvictionEvent
    thesis_less_order_detected: bool = False
    order_to_non_watchlist: bool = False
    unhedged_position_detected: bool = False    # #27: filled, no stop after 2s
    stale_data_trade_attempts: int = 0          # #28
    decision_timeout_rate: float = 0.0          # #29
    # config-derived thresholds
    daily_loss_limit_pct: float = 0.05
    drawdown_halt_pct: float = 0.20
    consecutive_loss_cooldown: int = 5
    consecutive_loss_halt_day: int = 8
    decision_timeout_halt_pct: float = 0.25


@dataclass
class Halt:
    number: int
    name: str
    scope: HaltScope
    reason: str


# Each rule: (number, name, predicate(state)->bool, scope, reason)
_RULES: List = [
    (1, "daily_loss_limit",
     lambda s: s.day_pnl <= -s.daily_loss_limit_pct * s.session_start_equity,
     HaltScope.HALT_SESSION, "daily loss <= -5% of session-start equity"),
    (2, "drawdown_from_ath",
     lambda s: s.equity <= (1 - s.drawdown_halt_pct) * s.ath_equity,
     HaltScope.HALT_UNTIL_RESUME, "equity <= -20% from all-time high"),
    (3, "catastrophic",
     lambda s: s.equity <= s.catastrophic_floor,
     HaltScope.HALT_INDEFINITE, "equity <= catastrophic floor ($1,050)"),
    (4, "mcp_failure",
     lambda s: s.mcp_heartbeat_age_s > 60,
     HaltScope.HALT_SESSION, "MCP heartbeat failed > 60s"),
    (5, "reconciliation_desync",
     lambda s: s.reconciliation_desync,
     HaltScope.HALT_SESSION, "broker vs internal desync > 1 cycle"),
    (6, "stale_feed_open_position",
     lambda s: s.has_open_position and s.data_feed_stale_age_s > 30,
     HaltScope.PAUSE_NEW_ORDERS, "data feed stale > 30s with an open position"),
    (11, "unexplained_quote_spike",
     lambda s: s.quote_spike_unexplained,
     HaltScope.PAUSE_TICKER, "quote moved >10% in 5s without volume + news"),
    (13, "pnl_velocity_anomaly",
     lambda s: s.pnl_velocity_anomaly,
     HaltScope.PAUSE_NEW_ORDERS, "P&L velocity anomaly (>3sigma) — verify state"),
    (8, "halt_flag",
     lambda s: s.halt_flag,
     HaltScope.HALT_SESSION, "HALT.flag present"),
    (9, "five_consecutive_losses",
     lambda s: s.consecutive_losses >= s.consecutive_loss_cooldown
               and s.consecutive_losses < s.consecutive_loss_halt_day,
     HaltScope.PAUSE_NEW_ORDERS, "5 consecutive losses -> 30-min cooldown"),
    (10, "eight_consecutive_losses",
     lambda s: s.consecutive_losses >= s.consecutive_loss_halt_day,
     HaltScope.HALT_SESSION, "8 consecutive losses -> halt for the day"),
    (12, "three_order_rejections",
     lambda s: s.consecutive_order_rejections >= 3,
     HaltScope.HALT_SESSION, "3 consecutive order rejections"),
    (14, "order_to_non_watchlist",
     lambda s: s.order_to_non_watchlist,
     HaltScope.PAUSE_NEW_ORDERS, "order to ticker not on today's watchlist"),
    (17, "order_rate_amplification",
     lambda s: s.order_rate_excessive,
     HaltScope.PAUSE_NEW_ORDERS, "order rate exceeds history (amplification freeze)"),
    (15, "self_test_failure",
     lambda s: s.self_test_failed,
     HaltScope.HALT_SESSION, "a self-test failed"),
    (21, "daily_llm_budget",
     lambda s: s.llm_daily_spent >= s.llm_daily_budget,
     HaltScope.BUDGET_PAUSE, "daily LLM budget exceeded ($5)"),
    (22, "monthly_llm_budget",
     lambda s: s.llm_monthly_spent >= s.llm_monthly_budget,
     HaltScope.BUDGET_PAUSE, "monthly LLM budget exceeded ($60)"),
    (25, "conviction_bypass",
     lambda s: s.conviction_bypass_detected,
     HaltScope.HALT_SESSION, "trade reached execution without a ConvictionEvent"),
    (26, "thesis_less_trade",
     lambda s: s.thesis_less_order_detected,
     HaltScope.HALT_SESSION, "OrderEvent with no stored thesis"),
    (27, "unhedged_position",
     lambda s: s.unhedged_position_detected,
     HaltScope.PAUSE_NEW_ORDERS, "filled position without a confirmed stop after 2s"),
    (28, "stale_data_trade_pattern",
     lambda s: s.stale_data_trade_attempts >= 3,
     HaltScope.HALT_SESSION, "3+ stale-data trade attempts (feed problem)"),
    (29, "latency_budget_breach_pattern",
     lambda s: s.decision_timeout_rate > s.decision_timeout_halt_pct,
     HaltScope.PAUSE_NEW_ORDERS, ">25% of decisions hit decision_timeout"),
]


def evaluate(state: KillswitchState) -> List[Halt]:
    """Return ALL fired halts (most severe first). Empty list == armed & clear."""
    fired = [Halt(n, name, scope, reason)
             for (n, name, pred, scope, reason) in _RULES if pred(state)]
    severity = {
        HaltScope.HALT_INDEFINITE: 0, HaltScope.HALT_UNTIL_RESUME: 1,
        HaltScope.HALT_SESSION: 2, HaltScope.PAUSE_NEW_ORDERS: 3,
        HaltScope.BUDGET_PAUSE: 4, HaltScope.PAUSE_TICKER: 5, HaltScope.NONE: 6,
    }
    fired.sort(key=lambda h: severity[h.scope])
    return fired


def most_severe(state: KillswitchState) -> Optional[Halt]:
    fired = evaluate(state)
    return fired[0] if fired else None
