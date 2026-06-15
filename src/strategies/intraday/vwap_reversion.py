"""
HOOD DaBang — VWAP Mean Reversion (Brief §8, strategy #3).

Window 10:30-15:00. A liquid name overextends >~2 ATR from session VWAP with no
fresh catalyst; RSI confirms the extreme (>75 short, <25 long); we fade back
toward VWAP. Stop beyond the extreme; target the VWAP touch. Range regimes only.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class VWAPReversion(Strategy):
    name = "vwap_reversion"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "range_low_vol": 1.0, "range_high_vol": 0.6, "transitional": 0.5,
        "bull_trend_low_vol": 0.2, "bear_trend_low_vol": 0.2,
        "bull_trend_high_vol": 0.1, "bear_trend_high_vol": 0.1, "crisis": 0.0,
    }
    wake = WakeCondition(timeframes=["1m"], session_windows=[("10:30", "15:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.vwap is None or ms.atr_14 is None or ms.rsi14 is None:
            return []
        if ms.has_catalyst and (ms.catalyst_age_min or 99) < 30:
            return []  # mean reversion wants NO fresh news
        price = ms.quote
        dev = price - ms.vwap
        extension_atr = abs(dev) / ms.atr_14 if ms.atr_14 else 0
        if extension_atr < 2.0:
            return []

        if dev < 0 and ms.rsi14 < 25:          # overextended DOWN -> fade up
            side = "long"
            stop = price - 0.5 * ms.atr_14
            target = ms.vwap
        elif dev > 0 and ms.rsi14 > 75:        # overextended UP -> fade down
            side = "short"
            stop = price + 0.5 * ms.atr_14
            target = ms.vwap
        else:
            return []

        risk = abs(price - stop)
        if risk <= 0 or abs(target - price) / risk < 1.0:
            return []
        return [self._mk(ms, side, price, stop, target, extension_atr)]

    def _mk(self, ms, side, entry, stop, target, ext):
        rr = abs(target - entry) / abs(entry - stop)
        rvol = ms.rvol or 1.0
        factors = {
            "setup_quality": round(_clamp(40 + 30 * min(2.0, ext / 2.0)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 55.0,   # MR is counter-trend by design
            "volume_confirmation": round(_clamp(30 + 35 * min(2.0, rvol)), 1),
            "catalyst_freshness": 20.0,            # intentionally no catalyst
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": round(_clamp(40 + 40 * min(1.5, rr) / 1.5), 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 1.0)], factors=factors,
                     requires_catalyst=False, expected_hold_min=45,
                     notes=f"VWAP-rev {side} ext={ext:.1f}ATR rsi={ms.rsi14:.0f}")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"
        if t >= "15:00":
            return Action(ActionType.EXIT, reason="vwap_rev_time_stop_1500")
        if ms.vwap is not None:                # target = VWAP touch
            if pos.side == "long" and ms.quote >= ms.vwap:
                return Action(ActionType.EXIT, reason="vwap_touched")
            if pos.side == "short" and ms.quote <= ms.vwap:
                return Action(ActionType.EXIT, reason="vwap_touched")
        return Action(ActionType.HOLD)
