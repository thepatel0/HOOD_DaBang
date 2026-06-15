"""
HOOD DaBang — Initial Balance Breakout (Brief §8, strategy #2).

The first 60 minutes establish the day's "initial balance" (IB). A break of an IB
extreme on volume tends to continue. Enter on the break; stop the opposite side
of the IB. Trend regimes.
"""
from __future__ import annotations

from typing import List, Optional

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _initial_balance(bars) -> Optional[tuple]:
    ib = [b for b in bars if "09:30" <= b.ts[11:16] < "10:30"]
    if not ib:
        return None
    return max(b.h for b in ib), min(b.l for b in ib)


class InitialBalanceBreakout(Strategy):
    name = "ibb"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bear_trend_low_vol": 0.7,
        "bull_trend_high_vol": 0.6, "bear_trend_high_vol": 0.6,
        "transitional": 0.4, "range_low_vol": 0.3, "range_high_vol": 0.2, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["5m"], session_windows=[("10:30", "15:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.atr_1m is None:
            return []
        bars = ms.bars.get("1m") or ms.bars.get("5m") or []
        ib = _initial_balance(bars)
        if ib is None:
            return []
        ib_high, ib_low = ib
        price = ms.quote
        buf = 0.1 * ms.atr_1m

        if price > ib_high:
            side, stop = "long", ib_low - buf
            risk = price - stop
            target = price + 1.5 * risk
        elif price < ib_low:
            side, stop = "short", ib_high + buf
            risk = stop - price
            target = price - 1.5 * risk
        else:
            return []
        if risk <= 0:
            return []
        return [self._mk(ms, side, price, stop, target, ib_high - ib_low)]

    def _mk(self, ms, side, entry, stop, target, ib_range):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        factors = {
            "setup_quality": round(_clamp(50 + 25 * min(2.0, rvol)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": round(60 if (ms.ema20 and (
                (side == "long" and entry > ms.ema20) or
                (side == "short" and entry < ms.ema20))) else 35, 1),
            "volume_confirmation": round(_clamp(30 + 35 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(40 if ms.has_catalyst else 25, 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(40 + 40 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 0.5)], factors=factors,
                     requires_catalyst=False, expected_hold_min=120,
                     notes=f"IBB {side} ib_range={ib_range:.2f}")

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
