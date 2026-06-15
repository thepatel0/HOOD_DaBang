"""
HOOD DaBang — screener (Brief §17, §26 screener).

Deterministic, $0 universe -> watchlist filtering: liquidity (price band, ADV),
volatility (ATR%), and ranking by pre-market gap or intraday RVOL. Excludes penny
stocks (<$5), illiquid names (<1M ADV), and the dead tape. Produces at most
`watchlist_max_names`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Candidate:
    ticker: str
    price: float
    adv_shares: float
    atr_pct: float                 # ATR / price
    gap_pct: float = 0.0           # pre-market gap
    rvol: float = 1.0              # intraday relative volume


class Screener:
    def __init__(self, cfg: dict):
        s = cfg["screener"]
        self.price_min = s["universe_price_min"]
        self.price_max = s["universe_price_max"]
        self.min_adv = s["universe_min_adv_shares"]
        self.min_atr_pct = s["universe_min_atr_pct"]
        self.gap_min = s["premarket_gap_min_pct"]
        self.rvol_min = s["intraday_rvol_min"]
        self.max_names = s["watchlist_max_names"]

    def passes_liquidity(self, c: Candidate) -> bool:
        return (self.price_min <= c.price <= self.price_max
                and c.adv_shares >= self.min_adv
                and c.atr_pct >= self.min_atr_pct)

    def filter_universe(self, candidates: List[Candidate]) -> List[Candidate]:
        return [c for c in candidates if self.passes_liquidity(c)]

    def premarket_watchlist(self, candidates: List[Candidate]) -> List[Candidate]:
        eligible = [c for c in self.filter_universe(candidates)
                    if abs(c.gap_pct) >= self.gap_min]
        eligible.sort(key=lambda c: abs(c.gap_pct), reverse=True)
        return eligible[:self.max_names]

    def intraday_watchlist(self, candidates: List[Candidate]) -> List[Candidate]:
        eligible = [c for c in self.filter_universe(candidates)
                    if c.rvol >= self.rvol_min]
        eligible.sort(key=lambda c: c.rvol, reverse=True)
        return eligible[:self.max_names]

    def combined_watchlist(self, candidates: List[Candidate]) -> List[str]:
        """Union of pre-market gappers and intraday RVOL leaders, capped."""
        names: List[str] = []
        seen = set()
        for c in self.premarket_watchlist(candidates) + self.intraday_watchlist(candidates):
            if c.ticker not in seen:
                seen.add(c.ticker)
                names.append(c.ticker)
        return names[:self.max_names]
