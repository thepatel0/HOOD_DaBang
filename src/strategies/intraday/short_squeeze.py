"""
HOOD DaBang — Short Squeeze (Brief §8, strategy #13).

High short interest (>20% of float) + RVOL >3x + a break of a key technical level.
HALF size, wider stop, tight 60-min time stop. High-variance; cap one/day. Needs
short_interest_pct (from FINRA/feed); abstains when absent.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class ShortSqueeze(Strategy):
    name = "short_squeeze"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 0.8, "bull_trend_high_vol": 1.0,
        "range_high_vol": 0.7, "transitional": 0.5, "range_low_vol": 0.4,
        "bear_trend_low_vol": 0.3, "bear_trend_high_vol": 0.4, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["5m"], min_rvol=3.0,
                         session_windows=[("09:45", "15:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.short_interest_pct is None or ms.atr_14 is None:
            return []
        if ms.short_interest_pct < 0.20 or (ms.rvol or 0) < 3.0:
            return []
        bars = ms.bars.get("5m") or ms.bars.get("1m") or []
        if len(bars) < 6:
            return []
        recent_high = max(b.h for b in bars[-6:-1])
        price = ms.quote
        if price <= recent_high:                 # must be breaking a key level up
            return []
        stop = price - 1.0 * ms.atr_14           # wider stop
        risk = price - stop
        if risk <= 0:
            return []
        target = price + 2.0 * risk
        return [self._mk(ms, price, stop, target)]

    def _mk(self, ms, entry, stop, target):
        rr = abs(target - entry) / abs(entry - stop)
        si = ms.short_interest_pct
        factors = {
            "setup_quality": round(_clamp(40 + 150 * (si - 0.20)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 55.0,
            "volume_confirmation": round(_clamp(40 + 20 * min(3.0, ms.rvol or 0)), 1),
            "catalyst_freshness": round(40 if ms.has_catalyst else 30, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(50 + 30 * min(2.0, rr) / 2.0), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side="long", entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=60,
                     notes=f"Squeeze SI={si:.0%} rvol={ms.rvol:.1f} HALF-size")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 60:                  # tight 60-min time stop
            return Action(ActionType.EXIT, reason="squeeze_time_stop")
        if pos.targets and ms.quote >= pos.targets[0][0]:
            return Action(ActionType.SCALE_OUT, reason="t1", fraction=0.5,
                          new_stop=pos.entry_price)
        return Action(ActionType.HOLD)
