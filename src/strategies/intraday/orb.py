"""
HOOD DaBang — Opening Range Breakout (Brief §8, strategy #1).

Window 09:35-10:00 ET entries; exits by 15:30. Opening range = first 5/15 min
high/low. Requires a catalyst OR high pre-market RVOL. Long on a 1-min close
above OR-high with volume confirmation; short mirrors. Stop = opposite side of
OR +/- 0.1*ATR. Scale 50% at 1.5R, trail the rest at the 9-EMA. Favored in trend
regimes, avoided in range.

Pure logic over a MarketState. Deterministic, $0, backtest==live.
"""
from __future__ import annotations

from typing import List

from ..base import (
    Strategy, MarketState, Setup, Position, Action, ActionType, WakeCondition,
)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


class OpeningRangeBreakout(Strategy):
    name = "orb"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "bull_trend_low_vol": 1.0, "bull_trend_high_vol": 0.7,
        "bear_trend_low_vol": 0.6, "bear_trend_high_vol": 0.5,
        "range_low_vol": 0.3, "range_high_vol": 0.2,
        "crisis": 0.0, "transitional": 0.4,
    }
    wake = WakeCondition(timeframes=["1m"], requires_catalyst=False,
                         session_windows=[("09:35", "10:00")])

    def __init__(self, recent_expectancy_score: float = 50.0):
        # injected by the controller from strategy_stats; neutral default
        self.recent_expectancy_score = recent_expectancy_score

    # ----- entry --------------------------------------------------------- #
    def scan(self, ms: MarketState) -> List[Setup]:
        if ms.opening_range_high is None or ms.opening_range_low is None:
            return []
        last = ms.last("1m")
        if last is None or ms.atr_1m is None:
            return []

        # catalyst OR strong RVOL is the precondition (Brief)
        rvol = ms.rvol or 0.0
        has_precondition = ms.has_catalyst or rvol >= 1.5
        if not has_precondition:
            return []

        orh, orl = ms.opening_range_high, ms.opening_range_low
        buf = 0.1 * ms.atr_1m
        setups: List[Setup] = []

        # LONG: 1-min close above OR-high
        if last.c > orh:
            entry = last.c
            stop = orl - buf
            risk = entry - stop
            if risk > 0:
                t1 = entry + 1.5 * risk
                setups.append(self._mk(ms, "long", entry, stop, t1, orh, rvol))

        # SHORT: 1-min close below OR-low (mirror)
        elif last.c < orl:
            entry = last.c
            stop = orh + buf
            risk = stop - entry
            if risk > 0:
                t1 = entry - 1.5 * risk
                setups.append(self._mk(ms, "short", entry, stop, t1, orl, rvol))

        return setups

    def _mk(self, ms: MarketState, side: str, entry: float, stop: float,
            t1: float, or_level: float, rvol: float) -> Setup:
        # --- deterministic conviction factor scoring (0-100) ---
        # break cleanliness: how far beyond the OR level the close is, in ATRs
        atr = ms.atr_1m or 0.01
        break_atrs = abs(entry - or_level) / atr
        setup_quality = _clamp(40 + 40 * min(1.5, break_atrs) / 1.5)

        regime_fit = _clamp(100 * self.regime_weight(ms.regime))

        # multi-timeframe confluence: price on the trend side of EMAs
        conf = 50.0
        if ms.ema20 is not None:
            if side == "long" and entry > ms.ema20:
                conf = 80.0
            elif side == "short" and entry < ms.ema20:
                conf = 80.0
            else:
                conf = 30.0
        mtf = conf

        volume_conf = _clamp(30 + 35 * min(2.0, rvol))  # rvol 2.0 -> 100

        if ms.has_catalyst:
            age = ms.catalyst_age_min if ms.catalyst_age_min is not None else 30
            fresh = _clamp(100 - 4 * age) if age <= 25 else 20
            catalyst = _clamp(0.5 * fresh + 0.5 * min(100, 40 * ms.catalyst_sources))
        else:
            catalyst = 25.0  # rvol-driven, no hard catalyst

        spread = ms.spread_pct or 0.0
        liq = _clamp(100 - spread * 30000)  # 0.3% spread -> ~10
        if ms.adv_shares and ms.adv_shares < 1_000_000:
            liq *= 0.5

        rr = abs(t1 - entry) / abs(entry - stop) if entry != stop else 0
        rrg = _clamp(40 + 40 * min(1.5, rr) / 1.5)

        factors = {
            "setup_quality": round(setup_quality, 1),
            "regime_fit": round(regime_fit, 1),
            "multi_timeframe_confluence": round(mtf, 1),
            "volume_confirmation": round(volume_conf, 1),
            "catalyst_freshness": round(catalyst, 1),
            "liquidity_spread": round(liq, 1),
            "risk_reward_geometry": round(rrg, 1),
            "strategy_recent_expectancy": round(self.recent_expectancy_score, 1),
        }
        return Setup(
            ticker=ms.ticker, strategy=self.name, version=self.version, side=side,
            entry_price=round(entry, 2), stop_price=round(stop, 2),
            targets=[(round(t1, 2), 0.5)], factors=factors,
            requires_catalyst=False, expected_hold_min=90,
            notes=f"ORB {side} OR[{ms.opening_range_low},{ms.opening_range_high}] rvol={rvol:.1f}",
        )

    # ----- management ---------------------------------------------------- #
    def manage(self, pos: Position, ms: MarketState) -> Action:
        t = ms.now_et[11:16] if len(ms.now_et) >= 16 else "00:00"

        # time stop: flatten intraday by 15:30
        if t >= "15:30":
            return Action(ActionType.EXIT, reason="orb_time_stop_1530", fraction=1.0)

        price = ms.quote
        r = abs(pos.entry_price - pos.stop_price)
        if r <= 0:
            return Action(ActionType.HOLD)

        # invalidation: loses VWAP against the position
        if ms.vwap is not None:
            if pos.side == "long" and price < ms.vwap:
                return Action(ActionType.EXIT, reason="lost_vwap", fraction=1.0)
            if pos.side == "short" and price > ms.vwap:
                return Action(ActionType.EXIT, reason="reclaimed_vwap", fraction=1.0)

        # T1: scale 50% at 1.5R and move stop to break-even
        if pos.targets:
            t1 = pos.targets[0][0]
            hit = (price >= t1) if pos.side == "long" else (price <= t1)
            if hit and pos.bars_held >= 0:
                return Action(ActionType.SCALE_OUT, reason="t1_1.5R", fraction=0.5,
                              new_stop=pos.entry_price)

        # trail the runner at the 9-EMA once past entry
        if ms.ema9 is not None:
            if pos.side == "long" and ms.ema9 > pos.stop_price and price > pos.entry_price:
                return Action(ActionType.MOVE_STOP, reason="trail_ema9", new_stop=ms.ema9)
            if pos.side == "short" and ms.ema9 < pos.stop_price and price < pos.entry_price:
                return Action(ActionType.MOVE_STOP, reason="trail_ema9", new_stop=ms.ema9)

        return Action(ActionType.HOLD)
