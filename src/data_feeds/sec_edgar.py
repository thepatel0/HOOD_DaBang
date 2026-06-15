"""
HOOD DaBang — SEC EDGAR feed (Brief §17, §26.16).

Form 4 insider transactions (free JSON endpoint), parsed to Form4Txn for the
InsiderAnalyst, cached by accession number (never re-parse the same filing). The
real fetcher MUST send a proper descriptive User-Agent and respect SEC fair-use
rate limits. Fetcher injected for offline tests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from ..analysts_local.insider import Form4Txn

USER_AGENT = "HoodDabang/1.0 (contact: operator@example.com)"
FORM4_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def httpx_fetch(cik: str) -> List[dict]:
    """Real fetcher (guarded import). Returns a list of raw Form-4 txn dicts.
    NOTE: the real EDGAR ownership data is XML per accession; this returns the
    normalized transaction list our parser expects, to be wired against the live
    endpoint with the proper User-Agent."""
    import httpx
    url = FORM4_URL.format(cik=str(cik).zfill(10))
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.json().get("form4_transactions", [])


class SecEdgarFeed:
    def __init__(self, fetcher: Callable[[str], List[dict]] = httpx_fetch,
                 ttl_s: int = 3600, clock: Callable[[], float] = time.time):
        self.fetcher = fetcher
        self.ttl_s = ttl_s
        self.clock = clock
        self._cache: Dict[str, tuple] = {}
        self._seen_accessions: set = set()

    def fetch_form4(self, cik: str) -> List[Form4Txn]:
        cached = self._cache.get(cik)
        if cached and (self.clock() - cached[0]) < self.ttl_s:
            return cached[1]
        try:
            raw = self.fetcher(cik)
        except Exception:
            return cached[1] if cached else []      # degrade to cache / empty

        txns: List[Form4Txn] = []
        for t in raw:
            acc = t.get("accession")
            if acc and acc in self._seen_accessions:
                continue
            if acc:
                self._seen_accessions.add(acc)
            txns.append(Form4Txn(
                insider=t.get("insider", "?"), role=t.get("role", "?"),
                side=t.get("side", "buy"), dollars=float(t.get("dollars", 0) or 0),
                pct_of_holdings=float(t.get("pct_of_holdings", 0) or 0),
                days_ago=int(t.get("days_ago", 0) or 0)))
        self._cache[cik] = (self.clock(), txns)
        return txns


@dataclass
class MacroSnapshot:
    series: Dict[str, float]


class FredFeed:
    """Macro series from FRED (rates, yields, credit spreads, USD). Cached;
    degrades to last snapshot. Fetcher injected."""
    def __init__(self, fetcher: Callable[[str], float] = None, ttl_s: int = 3600,
                 clock: Callable[[], float] = time.time):
        self.fetcher = fetcher
        self.ttl_s = ttl_s
        self.clock = clock
        self._cache: Dict[str, tuple] = {}

    def get(self, series_id: str) -> Optional[float]:
        cached = self._cache.get(series_id)
        if cached and (self.clock() - cached[0]) < self.ttl_s:
            return cached[1]
        if self.fetcher is None:
            return cached[1] if cached else None
        try:
            v = self.fetcher(series_id)
        except Exception:
            return cached[1] if cached else None
        self._cache[series_id] = (self.clock(), v)
        return v


@dataclass
class EarningsEvent:
    ticker: str
    date: str
    timing: str          # "BMO" | "AMC"


class EarningsCalendar:
    """Earnings calendar (Nasdaq/Yahoo free JSON). Maps a ticker to its next/last
    earnings, used to set days_since_earnings on MarketState. Fetcher injected."""
    def __init__(self, fetcher: Callable[[str], List[dict]] = None,
                 ttl_s: int = 21600, clock: Callable[[], float] = time.time):
        self.fetcher = fetcher
        self.ttl_s = ttl_s
        self.clock = clock
        self._cache: Optional[tuple] = None

    def events(self, date: str) -> List[EarningsEvent]:
        if self._cache and (self.clock() - self._cache[0]) < self.ttl_s:
            return self._cache[1]
        if self.fetcher is None:
            return self._cache[1] if self._cache else []
        try:
            raw = self.fetcher(date)
        except Exception:
            return self._cache[1] if self._cache else []
        out = [EarningsEvent(e["ticker"], e.get("date", date), e.get("timing", "AMC"))
               for e in raw]
        self._cache = (self.clock(), out)
        return out

    def days_since_earnings(self, ticker: str, events: List[EarningsEvent],
                            today: str) -> Optional[int]:
        for e in events:
            if e.ticker == ticker:
                return 0 if e.date == today else None
        return None
