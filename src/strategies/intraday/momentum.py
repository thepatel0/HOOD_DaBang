"""
HOOD DaBang — Relative-Volume Momentum (Brief §8, strategy #6).

Window 10:00-14:00. A top-RVOL name trending on the 5-min (above a rising 9-EMA
and 20-EMA) pulls back to the 9-EMA; we enter the continuation. Stop below the
20-EMA; target 1.5R then trail. Trend, low-vol regimes.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class RelativeVolumeMomentum(Strategy):
    name = "momentum"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.6,
        "bear_trend_low_vol": 0.5, "bear_trend_high_vol": 0.4,
        "range_low_vol": 0.2, "range_high_vol": 0.1,
        "transitional": 0.4, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["5m"], min_rvol=1.5,
                         session_windows=[("10:00", "14:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if None in (ms.ema9, ms.ema20, ms.atr_14):
            return []
        rvol = ms.rvol or 0.0
        if rvol < 1.5:
            return []
        price = ms.quote
        atr = ms.atr_14

        uptrend = ms.ema9 > ms.ema20 and price > ms.ema20
        downtrend = ms.ema9 < ms.ema20 and price < ms.ema20
        near_ema9 = abs(price - ms.ema9) <= 0.4 * atr  # pullback to the 9-EMA

        if uptrend and near_ema9:
            side = "long"
            stop = ms.ema20 - 0.1 * atr
            risk = price - stop
            target = price + 1.5 * risk
        elif downtrend and near_ema9:
            side = "short"
            stop = ms.ema20 + 0.1 * atr
            risk = stop - price
            target = price - 1.5 * risk
        else:
            return []

        if risk <= 0:
            return []
        return [self._mk(ms, side, price, stop, target, rvol)]

    def _mk(self, ms, side, entry, stop, target, rvol):
        rr = abs(target - entry) / abs(entry - stop)
        ema_sep = abs(ms.ema9 - ms.ema20) / (ms.atr_14 or 1)
        factors = {
            "setup_quality": round(_clamp(45 + 30 * min(1.5, ema_sep)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": round(_clamp(60 + 20 * min(1.5, ema_sep)), 1),
            "volume_confirmation": round(_clamp(30 + 35 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(_clamp(40 if ms.has_catalyst else 25), 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(40 + 40 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=60,
                     notes=f"Momentum {side} rvol={rvol:.1f} emaSep={ema_sep:.1f}ATR")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"
        if t >= "15:30":
            return Action(ActionType.EXIT, reason="momentum_time_stop_1530")
        price = ms.quote
        if pos.targets:
            t1 = pos.targets[0][0]
            hit = price >= t1 if pos.side == "long" else price <= t1
            if hit:
                return Action(ActionType.SCALE_OUT, reason="t1_1.5R", fraction=0.5,
                              new_stop=pos.entry_price)
        # trail the runner at the 9-EMA
        if ms.ema9 is not None:
            if pos.side == "long" and ms.ema9 > pos.stop_price and price > pos.entry_price:
                return Action(ActionType.MOVE_STOP, reason="trail_ema9", new_stop=ms.ema9)
            if pos.side == "short" and ms.ema9 < pos.stop_price and price < pos.entry_price:
                return Action(ActionType.MOVE_STOP, reason="trail_ema9", new_stop=ms.ema9)
        return Action(ActionType.HOLD)
