"""
HOOD DaBang — Quality Mean Reversion Swing (Brief §8, strategy #17).

High-quality large-caps that drop on indiscriminate selling recover within a
week. Enter an S&P-100 constituent with RSI(2) < 5 AND price within 5% of the
200-day SMA AND no fresh negative catalyst. Hold 3-5 days; revert to the 5-day
SMA, 3-day time stop, or -1.5R. Size 0.75%.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class QualityMeanReversion(Strategy):
    name = "quality_mean_reversion"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "range_low_vol": 1.0, "range_high_vol": 0.6, "bull_trend_low_vol": 0.6,
        "transitional": 0.5, "bear_trend_low_vol": 0.5,
        "bull_trend_high_vol": 0.3, "bear_trend_high_vol": 0.2, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1D"])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if None in (ms.rsi2, ms.sma200, ms.atr_14):
            return []
        if ms.rsi2 >= 5:                          # extreme oversold only
            return []
        if abs(ms.quote - ms.sma200) / ms.sma200 > 0.05:  # within 5% of 200-SMA
            return []
        if ms.has_catalyst and (ms.catalyst_age_min or 999) < 1440:
            return []  # no FRESH negative catalyst (within a day)
        price = ms.quote
        stop = price - 1.5 * ms.atr_14
        risk = price - stop
        if risk <= 0:
            return []
        target = ms.sma50 if ms.sma50 and ms.sma50 > price else price + 1.5 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        rr = abs(target - entry) / abs(entry - stop)
        factors = {
            "setup_quality": round(_clamp(70 + (5 - ms.rsi2) * 4), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 60.0,
            "volume_confirmation": round(_clamp(40 + 20 * min(2.0, ms.rvol or 1)), 1),
            "catalyst_freshness": 20.0,           # wants NO fresh catalyst
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(45 + 30 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 1.0)], factors=factors,
                     requires_catalyst=False, expected_hold_min=5 * 390,
                     notes=f"QualMR RSI2={ms.rsi2:.1f}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 3:                    # 3-day time stop
            return Action(ActionType.EXIT, reason="qualmr_3day_stop")
        # revert to 5-day SMA target handled by intrabar target in the engine
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.EXIT, reason="reverted_to_sma")
        return Action(ActionType.HOLD)
