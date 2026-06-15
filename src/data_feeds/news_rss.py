"""
HOOD DaBang — news RSS feed (Brief §17, §3.7).

Pulls per-ticker headlines from free RSS (Yahoo Finance, MarketWatch, etc.) and
dedups by URL hash so the same article is never re-processed (the News Analyst's
classification cache keys on the same hash). Graceful degradation: a parse/network
error yields the last cached headlines flagged `degraded`.

The RSS parser is INJECTED (default feedparser) so this is testable offline.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

YAHOO_RSS = ("https://feeds.finance.yahoo.com/rss/2.0/headline"
             "?s={ticker}&region=US&lang=en-US")


@dataclass
class Headline:
    title: str
    link: str
    published: str
    url_hash: str
    ticker: str


@dataclass
class NewsResult:
    headlines: List[Headline]
    degraded: bool = False
    reason: str = ""


def url_hash(link: str) -> str:
    return hashlib.sha1(link.encode()).hexdigest()[:16]


def feedparser_fetch(url: str) -> List[dict]:
    import feedparser
    parsed = feedparser.parse(url)
    return [{"title": e.get("title", ""), "link": e.get("link", ""),
             "published": e.get("published", "")} for e in parsed.entries]


class NewsFeed:
    def __init__(self, fetcher: Callable[[str], List[dict]] = feedparser_fetch,
                 ttl_s: int = 300, clock: Callable[[], float] = time.time):
        self.fetcher = fetcher
        self.ttl_s = ttl_s
        self.clock = clock
        self._seen: Set[str] = set()                  # url hashes already returned
        self._cache: Dict[str, tuple] = {}            # ticker -> (epoch, headlines)

    def fetch(self, ticker: str, only_new: bool = True) -> NewsResult:
        cached = self._cache.get(ticker)
        if cached and (self.clock() - cached[0]) < self.ttl_s:
            return NewsResult(self._filter(cached[1], only_new))
        try:
            entries = self.fetcher(YAHOO_RSS.format(ticker=ticker))
        except Exception as e:
            if cached:
                return NewsResult(self._filter(cached[1], only_new), degraded=True,
                                  reason=f"fetch_error_served_stale:{type(e).__name__}")
            return NewsResult([], degraded=True, reason=f"fetch_error:{type(e).__name__}")

        headlines = [Headline(e["title"], e["link"], e.get("published", ""),
                              url_hash(e["link"]), ticker) for e in entries if e.get("link")]
        self._cache[ticker] = (self.clock(), headlines)
        return NewsResult(self._filter(headlines, only_new))

    def _filter(self, headlines: List[Headline], only_new: bool) -> List[Headline]:
        if not only_new:
            return list(headlines)
        fresh = [h for h in headlines if h.url_hash not in self._seen]
        for h in fresh:
            self._seen.add(h.url_hash)
        return fresh
