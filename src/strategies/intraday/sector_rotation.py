"""
HOOD DaBang — Sector Rotation intraday (Brief §8, strategy #12).

Identify the day's leading sector; within it, take the highest-RVOL liquid name
with a momentum/ORB-style entry. Intraday sector leadership persists for hours.
Needs the `sector_is_leader` flag (set by a cross-asset/sector analyst); abstains
otherwise. Bull-trend regimes.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class SectorRotation(Strategy):
    name = "sector_rotation"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.7,
        "transitional": 0.4, "range_low_vol": 0.3, "range_high_vol": 0.2,
        "bear_trend_low_vol": 0.3, "bear_trend_high_vol": 0.3, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["5m"], min_rvol=1.5,
                         session_windows=[("10:00", "14:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if not ms.sector_is_leader or None in (ms.ema9, ms.ema20, ms.atr_14):
            return []
        if (ms.rvol or 0) < 1.5:
            return []
        price = ms.quote
        # momentum-style entry: trending up, pullback to 9-EMA
        if not (ms.ema9 > ms.ema20 and price > ms.ema20):
            return []
        if abs(price - ms.ema9) > 0.5 * ms.atr_14:
            return []
        stop = ms.ema20 - 0.1 * ms.atr_14
        risk = price - stop
        if risk <= 0:
            return []
        target = price + 1.5 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        factors = {
            "setup_quality": round(_clamp(55 + 20 * min(2.0, rvol)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 70.0,   # sector + name alignment
            "volume_confirmation": round(_clamp(35 + 35 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(45 if ms.has_catalyst else 30, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(45 + 35 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=90,
                     notes=f"SectorRot {ms.sector} leader")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"
        if t >= "15:30":
            return Action(ActionType.EXIT, reason="time_stop_1530")
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.SCALE_OUT, reason="t1", fraction=0.5,
                          new_stop=pos.entry_price)
        if ms.ema9 is not None and ms.ema9 > pos.stop_price and ms.quote > pos.entry_price:
            return Action(ActionType.MOVE_STOP, reason="trail_ema9", new_stop=ms.ema9)
        return Action(ActionType.HOLD)
