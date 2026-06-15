"""
HOOD DaBang — Earnings Reaction Day-1 (Brief §8, strategy #7).

A stock that reported AMC yesterday or BMO today. After 15-30 min of price
discovery: if up strongly and holding above the open on volume -> continuation
long on a pullback to VWAP; if a gap-up reversed below the open -> short on a
VWAP retest. Tight ATR stop (max ~1.5%). Target 1.5-2R. Needs the earnings flag.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class EarningsReaction(Strategy):
    name = "earnings_reaction"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 0.9, "bull_trend_high_vol": 0.8,
        "range_low_vol": 0.7, "range_high_vol": 0.6, "transitional": 0.5,
        "bear_trend_low_vol": 0.6, "bear_trend_high_vol": 0.6, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["5m"], session_windows=[("09:50", "14:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def _is_earnings_window(self, ms: MarketState) -> bool:
        return ms.is_earnings_today or ms.days_since_earnings in (0, 1)

    def scan(self, ms: MarketState) -> List[Setup]:
        if not self._is_earnings_window(ms) or ms.vwap is None or ms.atr_14 is None:
            return []
        if ms.gap_pct is None:
            return []
        price = ms.quote
        bars = ms.bars.get("5m") or ms.bars.get("1m") or []
        if not bars:
            return []
        day_open = bars[0].o
        atr = ms.atr_14
        stop_dist = min(0.015 * price, 1.0 * atr)

        # continuation: up >5%, above open, near VWAP pullback
        if ms.gap_pct > 0.05 and price > day_open and abs(price - ms.vwap) <= 0.5 * atr:
            side = "long"
            stop = price - stop_dist
            target = price + 1.75 * stop_dist
        # reversal: gapped up but reversed below open, retesting VWAP from below
        elif ms.gap_pct > 0.05 and price < day_open and abs(price - ms.vwap) <= 0.5 * atr:
            side = "short"
            stop = price + stop_dist
            target = price - 1.75 * stop_dist
        else:
            return []
        risk = abs(price - stop)
        if risk <= 0:
            return []
        return [self._mk(ms, side, price, stop, target)]

    def _mk(self, ms, side, entry, stop, target):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        factors = {
            "setup_quality": round(_clamp(55 + 20 * min(2.0, rvol)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 60.0,
            "volume_confirmation": round(_clamp(40 + 30 * min(2.0, rvol)), 1),
            "catalyst_freshness": 70.0,           # earnings IS the catalyst
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(45 + 35 * min(2.0, rr) / 2.0), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=120,
                     notes=f"EarnReact {side} gap={ms.gap_pct:.1%}")

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
