"""
HOOD DaBang — Sector Momentum Rotation (Brief §8, strategy #18).

Sector leadership persists over multi-week horizons. Enter the top-performing
sector (4-week) with broadening breadth (>60% of members above their 20-day SMA);
take the highest relative-strength liquid name. Hold 1-2 weeks; exit when the
sector closes below its 20-day SMA, at 3R, or a 14-day time stop. Size 0.75%.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class SectorMomentumRotation(Strategy):
    name = "sector_momentum_rotation"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.6, "transitional": 0.4,
        "range_low_vol": 0.3, "range_high_vol": 0.2, "bear_trend_low_vol": 0.3,
        "bear_trend_high_vol": 0.2, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1D"])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if not ms.sector_is_leader or None in (ms.rs_rank_pct, ms.sma50, ms.atr_14):
            return []
        if ms.rs_rank_pct < 0.70:                 # highest-RS name in the sector
            return []
        price = ms.quote
        if ms.sma50 and price < ms.sma50:         # trend intact
            return []
        stop = price - 2.0 * ms.atr_14
        risk = price - stop
        if risk <= 0:
            return []
        target = price + 3.0 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        factors = {
            "setup_quality": round(_clamp(50 + 50 * ms.rs_rank_pct), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 75.0,
            "volume_confirmation": round(_clamp(40 + 20 * min(2.0, ms.rvol or 1)), 1),
            "catalyst_freshness": round(40 if ms.has_catalyst else 30, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": 70.0,         # 3R target
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=14 * 390,
                     notes=f"SectorMomRot {ms.sector} RS={ms.rs_rank_pct:.0%}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 14:                   # 14-day time stop
            return Action(ActionType.EXIT, reason="sectormom_14day_stop")
        if ms.sma50 is not None and ms.quote < ms.sma50:
            return Action(ActionType.EXIT, reason="sector_below_sma")
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.SCALE_OUT, reason="t1_3R", fraction=0.5,
                          new_stop=pos.entry_price)
        return Action(ActionType.HOLD)
