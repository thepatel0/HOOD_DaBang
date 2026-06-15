"""
HOOD DaBang — OHLCV data feed (Brief §17, §3.7).

DataFeed interface (the abstraction live and historical both implement), plus a
CachedBarFeed with a local SQLite cache + TTL and graceful degradation: on a
fetch error it serves the last cached payload (and flags `degraded`) rather than
crashing the trading loop.

The actual network fetcher is INJECTED (default = yfinance) so the cache logic is
testable offline with a fake fetcher.
"""
from __future__ import annotations

import json
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..strategies.base import Bar


@dataclass
class FeedResult:
    bars: List[Bar]
    from_cache: bool
    degraded: bool = False
    reason: str = ""


class DataFeed(ABC):
    @abstractmethod
    def get_bars(self, ticker: str, interval: str, lookback_days: int) -> FeedResult:
        ...


def yf_fetch(ticker: str, interval: str, lookback_days: int) -> List[Bar]:
    """Default fetcher: yfinance OHLCV -> List[Bar]. Imported lazily so the
    bedrock never depends on yfinance."""
    import yfinance as yf
    period = f"{max(1, lookback_days)}d"
    df = yf.Ticker(ticker).history(period=period, interval=interval)
    bars: List[Bar] = []
    for idx, row in df.iterrows():
        bars.append(Bar(
            ts=idx.isoformat(), o=float(row["Open"]), h=float(row["High"]),
            l=float(row["Low"]), c=float(row["Close"]), v=float(row["Volume"])))
    return bars


def _ensure_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS bars_cache (key TEXT PRIMARY KEY, "
        "fetched_epoch REAL, payload TEXT)")
    conn.commit()


class CachedBarFeed(DataFeed):
    def __init__(self, fetcher: Callable[..., List[Bar]] = yf_fetch,
                 cache_conn: Optional[sqlite3.Connection] = None,
                 ttl_s: int = 300, clock: Callable[[], float] = time.time):
        self.fetcher = fetcher
        self.conn = cache_conn or sqlite3.connect(":memory:")
        _ensure_cache(self.conn)
        self.ttl_s = ttl_s
        self.clock = clock

    def _key(self, ticker, interval, lookback_days):
        return f"{ticker}|{interval}|{lookback_days}"

    def _read_cache(self, key):
        row = self.conn.execute(
            "SELECT fetched_epoch, payload FROM bars_cache WHERE key=?",
            (key,)).fetchone()
        if not row:
            return None
        fetched, payload = row
        bars = [Bar(**b) for b in json.loads(payload)]
        return fetched, bars

    def _write_cache(self, key, bars):
        payload = json.dumps([b.__dict__ for b in bars])
        self.conn.execute(
            "INSERT OR REPLACE INTO bars_cache (key, fetched_epoch, payload) "
            "VALUES (?,?,?)", (key, self.clock(), payload))
        self.conn.commit()

    def get_bars(self, ticker: str, interval: str = "1d",
                 lookback_days: int = 5) -> FeedResult:
        key = self._key(ticker, interval, lookback_days)
        cached = self._read_cache(key)

        # serve fresh cache (Brief §3.7: never refetch within TTL)
        if cached is not None and (self.clock() - cached[0]) < self.ttl_s:
            return FeedResult(cached[1], from_cache=True)

        # otherwise fetch; on failure, degrade to stale cache
        try:
            bars = self.fetcher(ticker, interval, lookback_days)
            if not bars and cached is not None:
                return FeedResult(cached[1], from_cache=True, degraded=True,
                                  reason="empty_fetch_served_stale")
            self._write_cache(key, bars)
            return FeedResult(bars, from_cache=False)
        except Exception as e:  # network/parse error -> graceful degradation
            if cached is not None:
                return FeedResult(cached[1], from_cache=True, degraded=True,
                                  reason=f"fetch_error_served_stale:{type(e).__name__}")
            return FeedResult([], from_cache=False, degraded=True,
                              reason=f"fetch_error_no_cache:{type(e).__name__}")
