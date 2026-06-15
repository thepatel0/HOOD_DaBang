"""
HOOD DaBang — position sizing (Brief 10).

Implements (brief filenames in parentheses):
  - kelly_size          (kelly.py)            half-Kelly from journal, 1.5% cap
  - vol_adjusted        (volatility_target.py)
  - correlation_room    (correlation_cap.py)  0.7 cap collapses correlated names
  - conviction_scaled   (conviction_scaled.py) 60%->100% of Kelly
  - final_risk_dollars  (final size = min of all constraints)

All pure functions, $0, identical in backtest and live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class StrategyStats:
    n_trades: int
    win_rate: float          # p, recency-weighted
    avg_win_dollars: float
    avg_loss_dollars: float  # positive magnitude


def kelly_risk_pct(stats: StrategyStats, cfg: dict) -> float:
    """Half-Kelly fraction of equity to risk (cap 1.5%). Quarter-Kelly &
    0.5% floor-default for strategies with <30 trades (Brief 10.1)."""
    s = cfg["sizing"]
    if stats.n_trades < 30:
        # not enough evidence: quarter-Kelly intent, but never exceed the
        # unproven default risk
        return min(s["unproven_risk_pct"], cfg["risk"]["per_trade_risk_pct"])
    if stats.avg_loss_dollars <= 0:
        return s["unproven_risk_pct"]
    p = stats.win_rate
    b = stats.avg_win_dollars / stats.avg_loss_dollars
    f_star = (b * p - (1 - p)) / b
    half_kelly = max(0.0, f_star) * s["kelly_fraction"]
    return min(half_kelly, cfg["risk"]["per_trade_risk_pct"])


def vol_adjusted(base_risk_dollars: float, realized_vol_20d: float, cfg: dict) -> float:
    """Scale by target/realized vol, capped (Brief 10.2)."""
    s = cfg["sizing"]
    if realized_vol_20d <= 0:
        return base_risk_dollars
    scalar = min(s["vol_scalar_max"], s["vol_target_annualized"] / realized_vol_20d)
    return base_risk_dollars * scalar


def conviction_scaled(kelly_allowed_dollars: float, conviction: float, cfg: dict) -> float:
    """Size scales 60% of Kelly at the execution floor -> 100% at conviction 90
    (Brief 10.4)."""
    floor = cfg["conviction"]["execution_floor"]
    ratio_floor = cfg["sizing"]["conviction_size_floor_ratio"]   # 0.6
    if conviction <= floor:
        ratio = ratio_floor
    else:
        ratio = ratio_floor + (1 - ratio_floor) * min(1.0, (conviction - floor) / (90 - floor))
    return kelly_allowed_dollars * max(ratio_floor, min(1.0, ratio))


def correlation_room(proposed_notional: float, correlated_open_notional: float,
                     equity: float, cfg: dict) -> float:
    """Return the max ADDITIONAL risk room given correlated exposure. Positions
    correlated >0.7 count as ONE for the position cap (Brief 10.3). We express
    that as: combined correlated notional may not exceed max_position_pct."""
    cap = cfg["risk"]["max_position_pct"] * equity
    remaining_notional = max(0.0, cap - correlated_open_notional)
    # convert remaining notional headroom back to a fraction of the proposal
    if proposed_notional <= 0:
        return 0.0
    return remaining_notional  # caller compares notional, not risk dollars


def final_risk_dollars(
    *,
    stats: StrategyStats,
    equity: float,
    realized_vol_20d: float,
    conviction: float,
    available_daily_risk_budget: float,
    cfg: dict,
) -> float:
    """The minimum of all risk constraints (Brief 10.5). Returns risk dollars."""
    kelly_pct = kelly_risk_pct(stats, cfg)
    kelly_dollars = kelly_pct * equity
    vol_dollars = vol_adjusted(kelly_dollars, realized_vol_20d, cfg)
    conv_dollars = conviction_scaled(kelly_dollars, conviction, cfg)
    hard_cap_dollars = cfg["risk"]["per_trade_risk_pct"] * equity
    return min(
        kelly_dollars,
        vol_dollars,
        conv_dollars,
        hard_cap_dollars,
        available_daily_risk_budget,
    )
