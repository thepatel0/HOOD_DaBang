"""
HOOD DaBang — Earnings Beat Follow-Through (Brief §8, strategy #16).

The magnitude of a beat correlates with sustained drift. Enter when Day-1 closes
above the open after a top-decile beat AND a guidance raise; buy next open. Hold
5 days; 1.5R, 5-day time stop, or a trailing 2-ATR stop. Size 0.75%.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class EarningsBeatFollowThrough(Strategy):
    name = "earnings_beat_followthrough"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.6, "range_low_vol": 0.5,
        "transitional": 0.3, "range_high_vol": 0.3, "bear_trend_low_vol": 0.4,
        "bear_trend_high_vol": 0.3, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1D"])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if None in (ms.sue, ms.atr_14) or ms.guidance_raised is None:
            return []
        if ms.days_since_earnings != 1:
            return []
        if ms.sue < 1.5 or not ms.guidance_raised:   # top-decile beat + raise
            return []
        bars = ms.bars.get("1D") or []
        if not bars or bars[-1].c <= bars[-1].o:      # Day-1 closed above open
            return []
        price = ms.quote
        stop = price - 2.0 * ms.atr_14
        risk = price - stop
        if risk <= 0:
            return []
        target = price + 1.5 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        factors = {
            "setup_quality": round(_clamp(50 + 20 * min(2.0, ms.sue)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 65.0,
            "volume_confirmation": round(_clamp(40 + 20 * min(2.0, ms.rvol or 1)), 1),
            "catalyst_freshness": 70.0,
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": 60.0,
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=5 * 390,
                     notes=f"BeatFT SUE={ms.sue:.1f} raise")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 5:
            return Action(ActionType.EXIT, reason="beatft_5day_stop")
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.SCALE_OUT, reason="t1", fraction=0.5,
                          new_stop=pos.entry_price)
        if ms.atr_14 is not None:                  # trailing 2-ATR stop
            trail = ms.quote - 2 * ms.atr_14
            if trail > pos.stop_price and ms.quote > pos.entry_price:
                return Action(ActionType.MOVE_STOP, reason="trail_2atr", new_stop=trail)
        return Action(ActionType.HOLD)
