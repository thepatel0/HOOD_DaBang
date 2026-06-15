"""
HOOD DaBang — full strategy registry factory (Brief §8).

Registers all 19 strategies and derives the regime-conditioned allocation matrix
from each strategy's own regime_preferences (consistent single source of truth):
allocation[regime][strategy] = regime_weight, normalized per regime. The weekly
review re-weights these by rolling per-regime expectancy.
"""
from __future__ import annotations

from typing import Dict, List

from .registry import StrategyRegistry
from .base import Strategy
from .intraday.orb import OpeningRangeBreakout
from .intraday.ibb import InitialBalanceBreakout
from .intraday.vwap_reversion import VWAPReversion
from .intraday.gap_fill import GapFill
from .intraday.gap_continuation import GapAndGo
from .intraday.momentum import RelativeVolumeMomentum
from .intraday.earnings_reaction import EarningsReaction
from .intraday.catalyst_scalp import CatalystScalp
from .intraday.range_compression import RangeCompression
from .intraday.hourly_sweep import HourlySweep
from .intraday.engulfing import MultiTimeframeEngulfing
from .intraday.sector_rotation import SectorRotation
from .intraday.short_squeeze import ShortSqueeze
from .swing.pead import PostEarningsDrift
from .swing.momentum_swing import MomentumSwing
from .swing.earnings_beat_followthrough import EarningsBeatFollowThrough
from .swing.quality_mean_reversion import QualityMeanReversion
from .swing.sector_momentum_rotation import SectorMomentumRotation
from .stat_arb.pairs import PairsStatArb

REGIMES = [
    "bull_trend_low_vol", "bull_trend_high_vol", "range_low_vol", "range_high_vol",
    "bear_trend_low_vol", "bear_trend_high_vol", "crisis", "transitional",
]

INTRADAY = [OpeningRangeBreakout, InitialBalanceBreakout, VWAPReversion, GapFill,
            GapAndGo, RelativeVolumeMomentum, EarningsReaction, CatalystScalp,
            RangeCompression, HourlySweep, MultiTimeframeEngulfing, SectorRotation,
            ShortSqueeze]
SWING = [PostEarningsDrift, MomentumSwing, EarningsBeatFollowThrough,
         QualityMeanReversion, SectorMomentumRotation]
STAT_ARB = [PairsStatArb]
ALL_STRATEGY_CLASSES = INTRADAY + SWING + STAT_ARB


def all_strategies() -> List[Strategy]:
    return [cls() for cls in ALL_STRATEGY_CLASSES]


def derive_allocations(strategies: List[Strategy]) -> Dict[str, Dict[str, float]]:
    """allocation[regime][strategy] normalized from regime_preferences."""
    alloc: Dict[str, Dict[str, float]] = {}
    for regime in REGIMES:
        weights = {s.name: s.regime_weight(regime) for s in strategies}
        total = sum(weights.values())
        if total > 0:
            alloc[regime] = {k: round(v / total, 4) for k, v in weights.items() if v > 0}
        else:
            alloc[regime] = {}
    return alloc


def build_full_registry(activation: str = "paper") -> StrategyRegistry:
    """Register all 19 strategies. Swing strategies stay 'development' until Day 30
    (intraday-only); intraday set to `activation` (default 'paper' — tradeable in
    sim, but 'live' still requires all five validation gates per strategy)."""
    strategies = all_strategies()
    reg = StrategyRegistry(regime_allocations=derive_allocations(strategies))
    swing_names = {cls().name for cls in SWING}
    for s in strategies:
        reg.register(s)
        if s.name in swing_names:
            continue  # swing unlocks after Day 30; leave in development
        reg.promote(s.name, activation)
    return reg
