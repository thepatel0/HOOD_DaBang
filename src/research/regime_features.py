"""
HOOD DaBang — real-data regime features (Brief §5.1).

Computes the regime feature vector [trend_50, trend_200, realized_vol, vix,
breadth] from real index data (SPY trend vs its SMAs, VIX level, 20-day realized
volatility, and market breadth), feeding the RegimeClassifier / deterministic
regime rule. Deterministic, $0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..strategies.base import Bar
from ..analysts_local.regime import deterministic_regime, RegimeClassifier


def _sma(closes: Sequence[float], n: int) -> Optional[float]:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def realized_vol_annualized(closes: Sequence[float], n: int = 20) -> float:
    if len(closes) < n + 1:
        return 0.0
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))
            if closes[i - 1] > 0]
    if len(rets) < 2:
        return 0.0
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


@dataclass
class RegimeFeatures:
    trend_50: float
    trend_200: float
    realized_vol: float
    vix: float
    breadth: float

    def as_vector(self) -> List[float]:
        return [self.trend_50, self.trend_200, self.realized_vol, self.vix, self.breadth]


def compute_features(spy_bars: List[Bar], vix: float = 18.0,
                     breadth: float = 0.5) -> Optional[RegimeFeatures]:
    closes = [b.c for b in spy_bars]
    if len(closes) < 50:
        return None
    price = closes[-1]
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200) or sma50
    trend_50 = (price - sma50) / sma50 if sma50 else 0.0
    trend_200 = (price - sma200) / sma200 if sma200 else 0.0
    rv = realized_vol_annualized(closes)
    return RegimeFeatures(trend_50, trend_200, rv, vix, breadth)


def detect_regime(spy_bars: List[Bar], vix: float = 18.0, breadth: float = 0.5,
                  classifier: Optional[RegimeClassifier] = None) -> str:
    """Return the regime label from real index data. Uses the trained classifier
    if provided, else the deterministic rule (the safe fallback)."""
    feats = compute_features(spy_bars, vix, breadth)
    if feats is None:
        return "transitional"          # not enough data -> conservative
    if classifier is not None:
        return classifier.classify(feats.as_vector()).label
    return deterministic_regime(*feats.as_vector())


def compute_breadth(names_bars: dict) -> float:
    """% of names trading above their own 50-day SMA (a breadth proxy)."""
    above = total = 0
    for bars in names_bars.values():
        closes = [b.c for b in bars]
        sma = _sma(closes, 50)
        if sma is None:
            continue
        total += 1
        if closes[-1] > sma:
            above += 1
    return (above / total) if total else 0.5
