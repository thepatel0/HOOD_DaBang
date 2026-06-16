"""
HOOD DaBang — Hourly Sweep Return-to-Open (Brief §8, strategy #10).

The current hour opens inside the prior hour's range, then sweeps the prior high
or low (a liquidity grab); on a reclaim of the swept level, price tends to return
to the current hour's open. Best on mechanically-behaved liquid names. Stop
0.15xATR beyond the sweep; target the current hour open.
"""
from __future__ import annotations

from typing import List, Optional

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _hour_key(ts: str) -> str:
    return ts[11:13]


class HourlySweep(Strategy):
    name = "hourly_sweep"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "range_low_vol": 1.0, "range_high_vol": 0.6, "transitional": 0.6,
        "bull_trend_low_vol": 0.5, "bear_trend_low_vol": 0.5,
        "bull_trend_high_vol": 0.3, "bear_trend_high_vol": 0.3, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1m"], session_windows=[("10:30", "15:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        bars = ms.bars.get("1m") or []
        if len(bars) < 30 or ms.atr_1m is None:
            return []
        cur_hour = _hour_key(ms.now_et)
        if not cur_hour.isdigit():
            return []                       # malformed/absent timestamp -> abstain
        cur_bars = [b for b in bars if _hour_key(b.ts) == cur_hour]
        prior_hour = f"{int(cur_hour) - 1:02d}"
        prior_bars = [b for b in bars if _hour_key(b.ts) == prior_hour]
        if len(cur_bars) < 3 or len(prior_bars) < 5:
            return []

        ph_high = max(b.h for b in prior_bars)
        ph_low = min(b.l for b in prior_bars)
        hour_open = cur_bars[0].o
        if not (ph_low < hour_open < ph_high):
            return []  # must open INSIDE the prior range

        price = ms.quote
        cur_high = max(b.h for b in cur_bars)
        cur_low = min(b.l for b in cur_bars)
        buf = 0.15 * ms.atr_1m

        # swept the high then reclaimed back below -> short toward open
        if cur_high > ph_high and price < ph_high:
            side, stop, target = "short", cur_high + buf, hour_open
            if not (stop > price > target):
                return []
        # swept the low then reclaimed back above -> long toward open
        elif cur_low < ph_low and price > ph_low:
            side, stop, target = "long", cur_low - buf, hour_open
            if not (stop < price < target):
                return []
        else:
            return []
        risk = abs(price - stop)
        if risk <= 0:
            return []
        # Note: this is a high-win-rate / lower-R return-to-open setup; geometry is
        # judged by the Conviction Gate's risk_reward_geometry factor, not a hard floor.
        return [self._mk(ms, side, price, stop, target)]

    def _mk(self, ms, side, entry, stop, target):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        factors = {
            "setup_quality": 65.0,
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 60.0,
            "volume_confirmation": round(_clamp(35 + 30 * min(2.0, rvol)), 1),
            "catalyst_freshness": 25.0,
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(45 + 35 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 1.0)], factors=factors,
                     requires_catalyst=False, expected_hold_min=45,
                     notes=f"HourlySweep {side} -> return to open")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 60:
            return Action(ActionType.EXIT, reason="sweep_time_stop")
        if pos.targets:
            t1 = pos.targets[0][0]
            hit = ms.quote >= t1 if pos.side == "long" else ms.quote <= t1
            if hit:
                return Action(ActionType.EXIT, reason="returned_to_open")
        return Action(ActionType.HOLD)
