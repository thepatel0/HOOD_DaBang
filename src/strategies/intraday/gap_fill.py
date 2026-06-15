"""
HOOD DaBang — Gap Fill mean reversion (Brief §8, strategy #4).

Window 09:30-10:30. A 1-3% pre-market gap on a liquid name with NO confirming
news tends to fill (~70% same day). Fade the gap toward the prior close. Stop
beyond the pre-market extreme. Any regime with contained volatility.
"""
from __future__ import annotations

from typing import List, Optional

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class GapFill(Strategy):
    name = "gap_fill"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "range_low_vol": 1.0, "bull_trend_low_vol": 0.6, "bear_trend_low_vol": 0.6,
        "range_high_vol": 0.3, "transitional": 0.5,
        "bull_trend_high_vol": 0.2, "bear_trend_high_vol": 0.2, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1m"], session_windows=[("09:30", "10:30")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.gap_pct is None or ms.prior_close is None or ms.atr_1m is None:
            return []
        if ms.has_catalyst and (ms.catalyst_age_min or 99) < 60:
            return []  # a catalyst-less gap is the edge; news-gaps continue, not fill
        g = ms.gap_pct
        if not (0.01 <= abs(g) <= 0.03):
            return []
        price = ms.quote
        buf = 0.1 * ms.atr_1m

        if g > 0:                       # gap UP -> fade short toward prior close
            side = "short"
            extreme = ms.premarket_high if ms.premarket_high else price + ms.atr_1m
            stop = extreme + buf
            target = ms.prior_close
            if not (stop > price > target):
                return []
        else:                           # gap DOWN -> fade long toward prior close
            side = "long"
            extreme = ms.premarket_low if ms.premarket_low else price - ms.atr_1m
            stop = extreme - buf
            target = ms.prior_close
            if not (stop < price < target):
                return []

        risk = abs(price - stop)
        if risk <= 0 or abs(target - price) / risk < 1.0:
            return []
        return [self._mk(ms, side, price, stop, target, abs(g))]

    def _mk(self, ms, side, entry, stop, target, gmag):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        factors = {
            "setup_quality": round(_clamp(50 + 1500 * (0.03 - gmag)), 1),  # smaller gap = cleaner fill
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 55.0,
            "volume_confirmation": round(_clamp(40 + 20 * min(2.0, rvol)), 1),
            "catalyst_freshness": 20.0,
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(40 + 40 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 1.0)], factors=factors,
                     requires_catalyst=False, expected_hold_min=45,
                     notes=f"GapFill {side} gap={gmag:.2%}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"
        if t >= "11:00":
            return Action(ActionType.EXIT, reason="gap_fill_time_stop")
        if ms.prior_close is not None:
            if pos.side == "long" and ms.quote >= ms.prior_close:
                return Action(ActionType.EXIT, reason="gap_filled")
            if pos.side == "short" and ms.quote <= ms.prior_close:
                return Action(ActionType.EXIT, reason="gap_filled")
        return Action(ActionType.HOLD)
