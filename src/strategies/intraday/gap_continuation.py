"""
HOOD DaBang — Gap and Go continuation (Brief §8, strategy #5).

Pre-market gap >3% WITH confirmed news. After a short consolidation off the open,
enter in the gap direction. Stop the opposite side of the consolidation; target
1.5R then trail. News-driven gaps with volume continue. Bull-trend regimes.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class GapAndGo(Strategy):
    name = "gap_continuation"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.7,
        "bear_trend_high_vol": 0.5, "transitional": 0.4,
        "range_low_vol": 0.2, "range_high_vol": 0.2,
        "bear_trend_low_vol": 0.3, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1m"], requires_catalyst=True,
                         session_windows=[("09:35", "10:30")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.gap_pct is None or ms.atr_1m is None:
            return []
        if not ms.has_catalyst or (ms.catalyst_age_min or 99) > 120:
            return []  # continuation needs a real, fresh catalyst
        g = ms.gap_pct
        if abs(g) < 0.03:
            return []
        bars = ms.bars.get("1m") or []
        if len(bars) < 6:
            return []
        # consolidation = last 5 bars' range after the open
        recent = bars[-5:]
        cons_high = max(b.h for b in recent)
        cons_low = min(b.l for b in recent)
        price = ms.quote
        buf = 0.1 * ms.atr_1m

        if g > 0 and price >= cons_high:           # break up in gap-up
            side, stop = "long", cons_low - buf
            risk = price - stop
            target = price + 1.5 * risk
        elif g < 0 and price <= cons_low:          # break down in gap-down
            side, stop = "short", cons_high + buf
            risk = stop - price
            target = price - 1.5 * risk
        else:
            return []
        if risk <= 0:
            return []
        return [self._mk(ms, side, price, stop, target, abs(g))]

    def _mk(self, ms, side, entry, stop, target, gmag):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        fresh = _clamp(100 - 1.5 * (ms.catalyst_age_min or 0))
        factors = {
            "setup_quality": round(_clamp(50 + 500 * (gmag - 0.03)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 70.0,
            "volume_confirmation": round(_clamp(35 + 35 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(_clamp(0.5 * fresh + 25 * ms.catalyst_sources), 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(40 + 40 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=True, expected_hold_min=90,
                     notes=f"GapAndGo {side} gap={gmag:.2%}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"
        if t >= "15:30":
            return Action(ActionType.EXIT, reason="time_stop_1530")
        if pos.targets:
            t1 = pos.targets[0][0]
            hit = ms.quote >= t1 if pos.side == "long" else ms.quote <= t1
            if hit:
                return Action(ActionType.SCALE_OUT, reason="t1_1.5R", fraction=0.5,
                              new_stop=pos.entry_price)
        if ms.ema9 is not None and pos.side == "long" and ms.ema9 > pos.stop_price \
                and ms.quote > pos.entry_price:
            return Action(ActionType.MOVE_STOP, reason="trail_ema9", new_stop=ms.ema9)
        return Action(ActionType.HOLD)
