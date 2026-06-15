"""
HOOD DaBang — Catalyst Scalp (Brief §8, strategy #8).

Anytime on a hard, fresh, multi-source catalyst (FDA, M&A, guidance, tier-1 desk
action). HALF size, tight stop (~0.5%), quick target (1R). Hit rate ~45-50% — the
edge is asymmetry/speed, not accuracy. `requires_llm_gating` relaxed for textbook
clean prints so it can still fire under budget-pause.
"""
from __future__ import annotations

from typing import List

from ..base import (Strategy, MarketState, Setup, Position, Action, ActionType,
                    WakeCondition)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


class CatalystScalp(Strategy):
    name = "catalyst_scalp"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = False           # relaxed for clean prints (Brief)
    regime_preferences = {
        "bull_trend_low_vol": 0.7, "bull_trend_high_vol": 0.8,
        "bear_trend_high_vol": 0.8, "range_high_vol": 0.7, "range_low_vol": 0.5,
        "transitional": 0.6, "bear_trend_low_vol": 0.6, "crisis": 0.2,
    }
    wake = WakeCondition(timeframes=["1m"], requires_catalyst=True)

    def __init__(self, recent_expectancy_score: float = 50.0):
        self.recent_expectancy_score = recent_expectancy_score

    def scan(self, ms: MarketState) -> List[Setup]:
        if not ms.has_catalyst or ms.atr_1m is None:
            return []
        if (ms.catalyst_age_min or 99) > 15 or ms.catalyst_sources < 2:
            return []  # fresh + multi-source only (anti-spoof)
        bars = ms.bars.get("1m") or []
        if len(bars) < 2:
            return []
        price = ms.quote
        # direction = the catalyst move so far (last bar vs prior)
        up = bars[-1].c >= bars[-2].c
        side = "long" if up else "short"
        stop_dist = max(0.005 * price, 0.5 * ms.atr_1m)  # ~0.5% tight stop
        if side == "long":
            stop = price - stop_dist
            target = price + stop_dist           # 1R quick target
        else:
            stop = price + stop_dist
            target = price - stop_dist
        return [self._mk(ms, side, price, stop, target)]

    def _mk(self, ms, side, entry, stop, target):
        rvol = ms.rvol or 1.0
        fresh = _clamp(100 - 6 * (ms.catalyst_age_min or 0))
        factors = {
            "setup_quality": round(_clamp(45 + 30 * min(2.0, rvol)), 1),
            "regime_fit": round(_clamp(100 * self.regime_weight(ms.regime)), 1),
            "multi_timeframe_confluence": 50.0,
            "volume_confirmation": round(_clamp(40 + 30 * min(2.0, rvol)), 1),
            "catalyst_freshness": round(_clamp(0.6 * fresh + 20 * ms.catalyst_sources), 1),
            "liquidity_spread": round(_clamp(100 - (ms.spread_pct or 0) * 30000), 1),
            "risk_reward_geometry": 55.0,    # 1R target by design
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(ticker=ms.ticker, strategy=self.name, version=self.version,
                     side=side, entry_price=round(entry, 2), stop_price=round(stop, 2),
                     targets=[(round(target, 2), 1.0)], factors=factors,
                     requires_catalyst=True, expected_hold_min=15,
                     notes=f"CatScalp {side} HALF-size age={ms.catalyst_age_min}m")

    def manage(self, pos: Position, ms: MarketState) -> Action:
        if pos.bars_held >= 15:                  # quick time stop
            return Action(ActionType.EXIT, reason="scalp_time_stop")
        if pos.targets:
            t1 = pos.targets[0][0]
            hit = ms.quote >= t1 if pos.side == "long" else ms.quote <= t1
            if hit:
                return Action(ActionType.EXIT, reason="scalp_target_1R")
        return Action(ActionType.HOLD)
