"""
HOOD DaBang — Technical Analyst (Tier 0, Brief §5.1).

Pure math over OHLCV. Computes the indicators and levels the strategies read
from MarketState: EMAs, RSI(Wilder), ATR(Wilder), session VWAP, MACD, Bollinger
band-width percentile, opening range, gap. Deterministic, $0, sub-second.

Indicator functions take numpy arrays and return the latest scalar (what
strategies need); helpers operate over the array for percentile work.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from ..strategies.base import Bar, MarketState


# --------------------------------------------------------------------------- #
# Indicator primitives (return the latest value unless noted)                  #
# --------------------------------------------------------------------------- #
def ema_series(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) == 0:
        return values
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def ema(values: np.ndarray, period: int) -> Optional[float]:
    if len(values) == 0:
        return None
    return float(ema_series(values, period)[-1])


def rsi(closes: np.ndarray, period: int = 14) -> Optional[float]:
    if len(closes) <= period:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    # Wilder smoothing
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
        period: int = 14) -> Optional[float]:
    n = len(close)
    if n < 2:
        return None
    prev_close = close[:-1]
    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - prev_close),
        np.abs(low[1:] - prev_close),
    ])
    if len(tr) < period:
        return float(tr.mean()) if len(tr) else None
    # Wilder smoothing
    a = tr[:period].mean()
    for i in range(period, len(tr)):
        a = (a * (period - 1) + tr[i]) / period
    return float(a)


def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray,
         volume: np.ndarray) -> Optional[float]:
    if len(close) == 0 or volume.sum() == 0:
        return None
    typical = (high + low + close) / 3.0
    return float((typical * volume).sum() / volume.sum())


def macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    if len(closes) < slow:
        return None, None, None
    macd_line = ema_series(closes, fast) - ema_series(closes, slow)
    signal_line = ema_series(macd_line, signal)
    hist = macd_line - signal_line
    return float(macd_line[-1]), float(signal_line[-1]), float(hist[-1])


def bb_width_percentile(closes: np.ndarray, period: int = 20, k: float = 2.0,
                        lookback: int = 100) -> Optional[float]:
    """Current Bollinger band-width as a percentile (0..1) of its trailing
    distribution. Low percentile == squeeze (range-compression setups)."""
    if len(closes) < period + 1:
        return None
    widths = []
    start = max(period, len(closes) - lookback)
    for i in range(start, len(closes) + 1):
        window = closes[i - period:i]
        mu, sd = window.mean(), window.std()
        widths.append((2 * k * sd) / mu if mu else 0.0)
    widths = np.array(widths)
    current = widths[-1]
    return float((widths <= current).mean())


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _arrays(bars: List[Bar]):
    o = np.array([b.o for b in bars], dtype=float)
    h = np.array([b.h for b in bars], dtype=float)
    l = np.array([b.l for b in bars], dtype=float)
    c = np.array([b.c for b in bars], dtype=float)
    v = np.array([b.v for b in bars], dtype=float)
    return o, h, l, c, v


def opening_range(bars_1m: List[Bar], minutes: int = 5) -> Optional[tuple]:
    """High/low of the first `minutes` 1-min bars at/after 09:30 ET."""
    session = [b for b in bars_1m if "09:30" <= b.ts[11:16] < _add_minutes("09:30", minutes)]
    if not session:
        return None
    return max(b.h for b in session), min(b.l for b in session)


def _add_minutes(hhmm: str, minutes: int) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def rvol_proxy(volume: np.ndarray, lookback: int = 20) -> Optional[float]:
    """Volume of the latest bar vs the mean of the prior `lookback` bars.
    A pragmatic intraday RVOL proxy (true time-of-day RVOL needs a historical
    profile, supplied by the microstructure analyst when available)."""
    if len(volume) < 2:
        return None
    prior = volume[max(0, len(volume) - 1 - lookback):-1]
    if len(prior) == 0 or prior.mean() == 0:
        return None
    return float(volume[-1] / prior.mean())


# --------------------------------------------------------------------------- #
# The analyst                                                                  #
# --------------------------------------------------------------------------- #
class TechnicalAnalyst:
    """Tier 0. compute() populates a MarketState from raw bars + context."""

    def compute(self, ticker: str, now_et: str, quote: float,
                bars_by_tf: Dict[str, List[Bar]], *,
                bid: float = 0.0, ask: float = 0.0,
                prior_close: float = None, prior_high: float = None,
                prior_low: float = None, premarket_high: float = None,
                premarket_low: float = None, regime: str = "range_low_vol",
                has_catalyst: bool = False, catalyst_age_min: float = None,
                catalyst_sources: int = 0, adv_shares: float = None,
                or_minutes: int = 5) -> MarketState:
        ms = MarketState(ticker=ticker, now_et=now_et, quote=quote, bid=bid, ask=ask,
                         bars=bars_by_tf, regime=regime, has_catalyst=has_catalyst,
                         catalyst_age_min=catalyst_age_min,
                         catalyst_sources=catalyst_sources, adv_shares=adv_shares)
        if bid and ask:
            mid = (bid + ask) / 2
            ms.spread_pct = (ask - bid) / mid if mid else 0.0

        ms.prior_close, ms.prior_high, ms.prior_low = prior_close, prior_high, prior_low
        ms.premarket_high, ms.premarket_low = premarket_high, premarket_low
        if prior_close:
            bars1 = bars_by_tf.get("1m") or []
            open_px = bars1[0].o if bars1 else quote
            ms.gap_pct = (open_px - prior_close) / prior_close

        # primary intraday timeframe for most indicators
        bars1 = bars_by_tf.get("1m")
        if bars1:
            o, h, l, c, v = _arrays(bars1)
            ms.atr_1m = atr(h, l, c, 14)
            ms.vwap = vwap(h, l, c, v)
            ms.rvol = rvol_proxy(v)
            orr = opening_range(bars1, or_minutes)
            if orr:
                ms.opening_range_high, ms.opening_range_low = orr

        bars5 = bars_by_tf.get("5m") or bars1
        if bars5:
            o, h, l, c, v = _arrays(bars5)
            ms.ema9 = ema(c, 9)
            ms.ema20 = ema(c, 20)
            ms.rsi14 = rsi(c, 14)
            ms.bb_width_pctile = bb_width_percentile(c)

        bars_for_atr14 = bars_by_tf.get("5m") or bars1
        if bars_for_atr14:
            o, h, l, c, v = _arrays(bars_for_atr14)
            ms.atr_14 = atr(h, l, c, 14)

        return ms
