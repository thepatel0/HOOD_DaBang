"""
HOOD DaBang — Conviction Gate Stage-1 deterministic scorecard (Brief 6.2).

Each of 8 factors is scored 0-100 by upstream Tier-0 analysts; this module
weights them into a single 0-100 deterministic score. Weights are hot-reloaded
from config (must sum to 1.0; enforced by config.validate).

Pure math, $0, identical in backtest and live.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

FACTORS = [
    "setup_quality",
    "regime_fit",
    "multi_timeframe_confluence",
    "volume_confirmation",
    "catalyst_freshness",
    "liquidity_spread",
    "risk_reward_geometry",
    "strategy_recent_expectancy",
]


@dataclass
class Signal:
    """A strategy-proposed candidate with its Tier-0 factor scores (each 0-100)
    and the structured attributes the hard floors inspect (Brief 6.4)."""
    ticker: str
    strategy: str
    side: str
    factors: Dict[str, float]                 # the 8 FACTORS -> 0..100

    # hard-floor inputs (6.4)
    spread_pct: float = 0.0
    shares_at_risk_cap: int = 1               # 0 => stop too far for whole-share sizing
    requires_catalyst: bool = False
    has_catalyst: bool = False
    catalyst_age_min: Optional[float] = None
    catalyst_sources: int = 0
    is_large_move: bool = False
    regime: str = "range_low_vol"
    holding_window_spans_earnings: bool = False
    in_blackout_window: bool = False          # FOMC blackout / first 5m / last 10m
    open_positions_at_cap: bool = False
    daily_halt_active: bool = False           # loss limit / DD / budget killswitch

    det_score: float = 0.0                    # filled in by score()
    hard_floor_reason: Optional[str] = None   # set if a hard floor rejects it


def score(sig: Signal, weights: Dict[str, float]) -> float:
    """Weighted 0-100 deterministic score. Missing factor => 0 (fail-closed:
    a missing input cannot earn credit)."""
    total = 0.0
    for f in FACTORS:
        total += weights[f] * float(sig.factors.get(f, 0.0))
    sig.det_score = round(total, 4)
    return sig.det_score


# Strategies that genuinely run in crisis (Brief 8: only pairs/cash).
_CRISIS_OK_STRATEGIES = {"pairs", "cash"}


def hard_floor_reject(sig: Signal) -> Optional[str]:
    """Return a rejection reason if ANY hard floor (Brief 6.4) is violated,
    else None. These override the score entirely."""
    if sig.daily_halt_active:
        return "daily_halt_active"
    if sig.spread_pct > 0.003:
        return "spread_gt_0.3pct"
    if sig.shares_at_risk_cap <= 0:
        return "zero_whole_shares_at_risk_cap"
    if sig.requires_catalyst:
        if not sig.has_catalyst:
            return "catalyst_strategy_without_catalyst"
        if sig.catalyst_age_min is not None and sig.catalyst_age_min > 15:
            # stale catalyst allowed only with confirming volume (proxied by a
            # strong volume_confirmation factor)
            if sig.factors.get("volume_confirmation", 0) < 60:
                return "stale_catalyst_no_confirming_volume"
    if sig.is_large_move and sig.has_catalyst and sig.catalyst_sources < 2:
        return "single_source_catalyst_on_large_move"
    if sig.regime == "crisis" and sig.strategy not in _CRISIS_OK_STRATEGIES:
        return "crisis_regime_non_pairs"
    if sig.in_blackout_window:
        return "blackout_window"
    if sig.holding_window_spans_earnings:
        return "holding_window_spans_earnings"
    if sig.open_positions_at_cap:
        return "concurrency_cap"
    return None
