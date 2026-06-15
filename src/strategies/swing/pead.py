"""
HOOD DaBang — Post-Earnings Announcement Drift (Brief §8, strategy #14).

Bernard & Thomas (1989): a 30+ year anomaly. Enter Day 2 after earnings (skip
Day-1 noise) on a top-quintile beat (SUE > 1.0) with top-30% sector relative
strength. Hold 5-15 days; 1.5R on half, trail the daily 9-EMA, force-exit Day 15.
Size 0.75% risk. Swing — unlocks after Day 30 of live operation.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class PostEarningsDrift(Strategy):
    name = "pead"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.6,
        "range_low_vol": 0.5, "transitional": 0.3, "range_high_vol": 0.3,
        "bear_trend_low_vol": 0.4, "bear_trend_high_vol": 0.3, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1D"])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if None in (ms.sue, ms.rs_rank_pct, ms.atr_14):
            return []
        if ms.days_since_earnings != 2:           # Day 2 only (skip Day-1 noise)
            return []
        if ms.sue < 1.0 or ms.rs_rank_pct < 0.70:  # top-quintile beat, top-30% RS
            return []
        price = ms.quote
        stop = price - 1.5 * ms.atr_14            # daily ATR stop
        risk = price - stop
        if risk <= 0:
            return []
        target = price + 1.5 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        factors = {
            "setup_quality": round(_clamp(50 + 25 * min(2.0, ms.sue)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": round(_clamp(40 + 60 * ms.rs_rank_pct), 1),
            "volume_confirmation": round(_clamp(40 + 20 * min(2.0, ms.rvol or 1)), 1),
            "catalyst_freshness": 60.0,           # earnings beat
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": 60.0,
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=15 * 390,  # ~15 sessions
                     notes=f"PEAD SUE={ms.sue:.1f} RS={ms.rs_rank_pct:.0%}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 15:                   # force exit Day 15 (daily bars)
            return Action(ActionType.EXIT, reason="pead_15day_stop")
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.SCALE_OUT, reason="t1_1.5R", fraction=0.5,
                          new_stop=pos.entry_price)
        if ms.ema9 is not None and ms.ema9 > pos.stop_price and ms.quote > pos.entry_price:
            return Action(ActionType.MOVE_STOP, reason="trail_daily_ema9", new_stop=ms.ema9)
        return Action(ActionType.HOLD)
