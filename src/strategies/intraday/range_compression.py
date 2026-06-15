"""
HOOD DaBang — Range Compression / squeeze -> expansion (Brief §8, strategy #9).

When 5-min Bollinger band-width sits below the 20th percentile of its trailing
distribution (a squeeze), a range expansion follows with high probability. Enter
the first bar that breaks the consolidation on volume; stop the opposite side;
target ~2x the consolidation height. Low-vol regimes.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class RangeCompression(Strategy):
    name = "range_compression"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "range_low_vol": 1.0, "bull_trend_low_vol": 0.6, "bear_trend_low_vol": 0.5,
        "transitional": 0.6, "range_high_vol": 0.3,
        "bull_trend_high_vol": 0.2, "bear_trend_high_vol": 0.2, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["5m"], session_windows=[("09:45", "15:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.bb_width_pctile is None or ms.bb_width_pctile > 0.20:
            return []  # not a squeeze
        bars = ms.bars.get("5m") or ms.bars.get("1m") or []
        if len(bars) < 6:
            return []
        recent = bars[-6:-1]                       # the consolidation (exclude breakout bar)
        cons_high = max(b.h for b in recent)
        cons_low = min(b.l for b in recent)
        height = cons_high - cons_low
        if height <= 0:
            return []
        price = ms.quote
        rvol = ms.rvol or 0.0
        if rvol < 1.2:                             # need participation on the break
            return []

        if price > cons_high:
            side, stop, target = "long", cons_low, price + 2 * height
        elif price < cons_low:
            side, stop, target = "short", cons_high, price - 2 * height
        else:
            return []
        risk = abs(price - stop)
        if risk <= 0:
            return []
        return [self._mk(ms, side, price, stop, target, ms.bb_width_pctile, rvol)]

    def _mk(self, ms, side, entry, stop, target, pctile, rvol):
        rr = abs(target - entry) / abs(entry - stop)
        factors = {
            "setup_quality": round(_clamp(60 + 200 * (0.20 - pctile)), 1),  # tighter squeeze = better
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 60.0,
            "volume_confirmation": round(_clamp(30 + 35 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(40 if ms.has_catalyst else 25, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(50 + 30 * min(2.0, rr) / 2.0), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=60,
                     notes=f"Squeeze {side} bbpctile={pctile:.2f}")

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
