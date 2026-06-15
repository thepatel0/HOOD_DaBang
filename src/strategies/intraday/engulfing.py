"""
HOOD DaBang — Multi-Timeframe Engulfing (Brief §8, strategy #11).

A 15-min engulfing candle at a higher-timeframe support/resistance level on
volume >1.5x average. Enter the next bar; stop beyond the engulfing extreme;
target the prior swing. Engulfing reversals at HTF levels have documented edge.
"""
from __future__ import annotations

from typing import List, Optional

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class MultiTimeframeEngulfing(Strategy):
    name = "engulfing"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "range_low_vol": 0.8, "range_high_vol": 0.6, "transitional": 0.7,
        "bull_trend_low_vol": 0.6, "bear_trend_low_vol": 0.6,
        "bull_trend_high_vol": 0.5, "bear_trend_high_vol": 0.5, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["15m"], session_windows=[("09:45", "15:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def _htf_level(self, ms: MarketState, side: str) -> Optional[float]:
        # nearest HTF support (long) / resistance (short)
        levels = [x for x in (ms.sma50, ms.sma200, ms.prior_low if side == "long"
                              else ms.prior_high) if x is not None]
        return min(levels, key=lambda L: abs(L - ms.quote)) if levels else None

    def scan(self, ms: MarketState) -> List[Setup]:
        bars = ms.bars.get("15m") or []
        if len(bars) < 2 or ms.atr_14 is None:
            return []
        b0, b1 = bars[-2], bars[-1]
        rvol = ms.rvol or 0.0
        if rvol < 1.5:
            return []

        bull_engulf = (b0.c < b0.o and b1.c > b1.o and b1.c >= b0.o and b1.o <= b0.c)
        bear_engulf = (b0.c > b0.o and b1.c < b1.o and b1.c <= b0.o and b1.o >= b0.c)
        price = ms.quote

        if bull_engulf:
            level = self._htf_level(ms, "long")
            if level is None or abs(price - level) > 1.0 * ms.atr_14:
                return []
            side, stop = "long", b1.l - 0.1 * ms.atr_14
            risk = price - stop
            target = price + 2.0 * risk
        elif bear_engulf:
            level = self._htf_level(ms, "short")
            if level is None or abs(price - level) > 1.0 * ms.atr_14:
                return []
            side, stop = "short", b1.h + 0.1 * ms.atr_14
            risk = stop - price
            target = price - 2.0 * risk
        else:
            return []
        if risk <= 0:
            return []
        return [self._mk(ms, side, price, stop, target, rvol)]

    def _mk(self, ms, side, entry, stop, target, rvol):
        rr = abs(target - entry) / abs(entry - stop)
        factors = {
            "setup_quality": round(_clamp(55 + 20 * min(2.0, rvol)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 75.0,   # by construction (HTF level)
            "volume_confirmation": round(_clamp(40 + 30 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(35 if ms.has_catalyst else 25, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(50 + 30 * min(2.0, rr) / 2.0), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=90,
                     notes=f"Engulf {side} at HTF level")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"
        if t >= "15:30":
            return Action(ActionType.EXIT, reason="time_stop_1530")
        if pos.targets:
            t1 = pos.targets[0][0]
            hit = ms.quote >= t1 if pos.side == "long" else ms.quote <= t1
            if hit:
                return Action(ActionType.SCALE_OUT, reason="t1", fraction=0.5,
                              new_stop=pos.entry_price)
        return Action(ActionType.HOLD)
