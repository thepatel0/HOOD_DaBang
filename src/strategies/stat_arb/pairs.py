"""
HOOD DaBang — Pairs Statistical Arbitrage (Brief §8, strategy #19).

Two historically cointegrated names (e.g. MA/V, XOM/CVX). Compute the spread's
rolling z-score; when |z| > 2, long the underperformer and short the
outperformer; exit on reversion to 0, stop at |z| = 3. Market-neutral — the only
strategy that runs meaningfully in CRISIS (60% allocation) because it does not
depend on market direction.

Two-legged, so it has its own scan_pair interface rather than the single-name
scan(); the controller routes pairs through this path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..base import Strategy, MarketState, Setup, Position, Action, ActionType, WakeCondition


def rolling_zscore(spread: Sequence[float]) -> Optional[float]:
    """z of the latest spread value vs the window mean/std."""
    n = len(spread)
    if n < 20:
        return None
    mean = sum(spread) / n
    var = sum((x - mean) ** 2 for x in spread) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return None
    return (spread[-1] - mean) / sd


def hedge_ratio(prices_a: Sequence[float], prices_b: Sequence[float]) -> float:
    """OLS slope of a on b (no intercept) = sum(a*b)/sum(b*b)."""
    num = sum(a * b for a, b in zip(prices_a, prices_b))
    den = sum(b * b for b in prices_b)
    return num / den if den else 1.0


@dataclass
class PairLeg:
    ticker: str
    setup: Setup


class PairsStatArb(Strategy):
    name = "pairs"
    version = "1.0.0"
    activation_status = "development"
    requires_llm_gating = True
    regime_preferences = {
        "crisis": 1.0, "transitional": 0.6, "range_high_vol": 0.5,
        "range_low_vol": 0.3, "bear_trend_high_vol": 0.4, "bear_trend_low_vol": 0.3,
        "bull_trend_low_vol": 0.2, "bull_trend_high_vol": 0.2,
    }
    wake = WakeCondition(timeframes=["5m"])

    def __init__(self, recent_expectancy_score: float = 50.0,
                 entry_z: float = 2.0, exit_z: float = 0.0, stop_z: float = 3.0):
        self.recent_expectancy_score = recent_expectancy_score
        self.entry_z, self.exit_z, self.stop_z = entry_z, exit_z, stop_z

    # single-name scan is a no-op; pairs uses scan_pair
    def scan(self, ms: MarketState) -> List[Setup]:
        return []

    def scan_pair(self, ticker_a: str, price_a: float, ticker_b: str, price_b: float,
                  prices_a: Sequence[float], prices_b: Sequence[float],
                  regime: str = "crisis") -> List[PairLeg]:
        beta = hedge_ratio(prices_a, prices_b)
        spread = [a - beta * b for a, b in zip(prices_a, prices_b)]
        z = rolling_zscore(spread)
        if z is None or abs(z) < self.entry_z:
            return []

        # z>0 => a rich vs b => short a, long b; z<0 => mirror
        # stop distance in price ~ how far to |z|=stop_z
        sd_spread = (spread[-1] - (z and (spread[-1] - z))) if z else 0
        legs: List[PairLeg] = []
        if z > 0:
            legs.append(self._leg(ticker_a, price_a, "short", z, regime))
            legs.append(self._leg(ticker_b, price_b, "long", z, regime))
        else:
            legs.append(self._leg(ticker_a, price_a, "long", z, regime))
            legs.append(self._leg(ticker_b, price_b, "short", z, regime))
        return legs

    def _leg(self, ticker, price, side, z, regime) -> PairLeg:
        # stop a fixed % away (the spread stop is enforced at the pair level)
        stop = price * (0.97 if side == "long" else 1.03)
        target = price * (1.02 if side == "long" else 0.98)
        factors = {
            "setup_quality": min(100.0, 50 + 15 * abs(z)),
            "regime_fit": 100 * self.regime_weight(regime),
            "multi_timeframe_confluence": 60.0,
            "volume_confirmation": 55.0,
            "catalyst_freshness": 30.0,
            "liquidity_spread": 85.0,
            "risk_reward_geometry": 55.0,
            "strategy_recent_expectancy": self.recent_expectancy_score,
        }
        s = Setup(ticker=ticker, strategy=self.name, version=self.version, side=side,
                  entry_price=round(price, 2), stop_price=round(stop, 2),
                  targets=[(round(target, 2), 1.0)], factors=factors,
                  requires_catalyst=False, expected_hold_min=240,
                  notes=f"Pairs leg z={z:.2f}")
        return PairLeg(ticker, s)

    def manage(self, pos: Position, ms: MarketState) -> Action:
        # pair exit is driven by spread reversion, signalled via ms context
        return Action(ActionType.HOLD)

    def should_exit_pair(self, z: float) -> Optional[str]:
        # exit when the spread has reverted toward 0 (within ~0.5 sigma) or hit
        # the divergence stop at 3 sigma.
        if abs(z) <= self.exit_z + 0.5:
            return "spread_reverted"
        if abs(z) >= self.stop_z:
            return "spread_stop_3sigma"
        return None
