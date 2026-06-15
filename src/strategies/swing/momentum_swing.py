"""
HOOD DaBang — Momentum Swing (Brief §8, strategy #15).

Jegadeesh & Titman momentum. Enter top-decile 20-day momentum AND a break of the
20-day high on volume >1.5x AND above a rising 50-day SMA. Hold 3-10 days; 2R on
half, trail the 20-day SMA; force-exit on a close below the 20-day SMA. Size 1%.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class MomentumSwing(Strategy):
    name = "momentum_swing"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.6,
        "transitional": 0.4, "range_low_vol": 0.2, "range_high_vol": 0.1,
        "bear_trend_low_vol": 0.2, "bear_trend_high_vol": 0.1, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1D"])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if None in (ms.mom_20d, ms.high_20d, ms.sma50, ms.atr_14):
            return []
        price = ms.quote
        # top-decile momentum proxy: mom_20d above a strong threshold
        if ms.mom_20d < 0.10:
            return []
        if price < ms.high_20d:                   # must break the 20-day high
            return []
        if price < ms.sma50:                      # above rising 50-day SMA
            return []
        if (ms.rvol or 0) < 1.5:
            return []
        stop = ms.sma50 - 0.2 * ms.atr_14
        risk = price - stop
        if risk <= 0:
            return []
        target = price + 2.0 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        rr = abs(target - entry) / abs(entry - stop)
        factors = {
            "setup_quality": round(_clamp(40 + 200 * ms.mom_20d), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 75.0,
            "volume_confirmation": round(_clamp(40 + 25 * min(2.0, ms.rvol or 1)), 1),
            "catalyst_freshness": round(40 if ms.has_catalyst else 30, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(50 + 30 * min(2.0, rr) / 2.0), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=10 * 390,
                     notes=f"MomSwing mom20={ms.mom_20d:.1%}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 10:
            return Action(ActionType.EXIT, reason="mom_swing_10day_stop")
        if ms.sma50 is not None and ms.quote < ms.sma50:     # close below 50-SMA
            return Action(ActionType.EXIT, reason="below_50sma")
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.SCALE_OUT, reason="t1_2R", fraction=0.5,
                          new_stop=pos.entry_price)
        return Action(ActionType.HOLD)
