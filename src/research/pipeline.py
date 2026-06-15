"""
HOOD DaBang — research pipeline / MarketState builder (Brief §16, §4.4).

The integration glue between raw data and the strategies: assembles a fully
populated MarketState by composing the Tier-0 analysts (technical, microstructure,
insider) and the feeds (news catalysts, earnings, short interest) into one
strongly-typed object the strategies and Conviction Gate consume.

All deterministic, $0. News classification (Tier 1) is the only optionally-LLM
input and is passed in already-classified so this stays $0 to run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..strategies.base import MarketState, Bar
from ..analysts_local.technical import TechnicalAnalyst
from ..analysts_local.microstructure import MicrostructureAnalyst, MicroResult


@dataclass
class TickerContext:
    """Per-ticker context the pipeline merges in (from feeds/analysts)."""
    prior_close: Optional[float] = None
    prior_high: Optional[float] = None
    prior_low: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    adv_shares: Optional[float] = None
    # catalysts (from news analyst, already classified -> $0 here)
    has_catalyst: bool = False
    catalyst_age_min: Optional[float] = None
    catalyst_sources: int = 0
    # earnings / short interest / sector (from feeds)
    days_since_earnings: Optional[int] = None
    is_earnings_today: bool = False
    short_interest_pct: Optional[float] = None
    sector: Optional[str] = None
    sector_is_leader: bool = False
    # swing daily context
    sue: Optional[float] = None
    rs_rank_pct: Optional[float] = None
    guidance_raised: Optional[bool] = None
    mom_20d: Optional[float] = None
    high_20d: Optional[float] = None
    rsi2: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    # microstructure refinement
    micro: Optional[MicroResult] = None


class ResearchPipeline:
    def __init__(self):
        self.ta = TechnicalAnalyst()
        self.micro = MicrostructureAnalyst()

    def build(self, ticker: str, now_et: str, quote: float,
              bars_by_tf: Dict[str, List[Bar]], regime: str,
              ctx: Optional[TickerContext] = None,
              bid: float = 0.0, ask: float = 0.0) -> MarketState:
        ctx = ctx or TickerContext()

        ms = self.ta.compute(
            ticker, now_et, quote, bars_by_tf, bid=bid, ask=ask,
            prior_close=ctx.prior_close, prior_high=ctx.prior_high,
            prior_low=ctx.prior_low, premarket_high=ctx.premarket_high,
            premarket_low=ctx.premarket_low, regime=regime,
            has_catalyst=ctx.has_catalyst, catalyst_age_min=ctx.catalyst_age_min,
            catalyst_sources=ctx.catalyst_sources, adv_shares=ctx.adv_shares)

        # microstructure refines RVOL when a proper time-of-day profile is given
        if ctx.micro is not None and ctx.micro.rvol is not None:
            ms.rvol = ctx.micro.rvol

        # merge swing/daily + event context
        ms.days_since_earnings = ctx.days_since_earnings
        ms.is_earnings_today = ctx.is_earnings_today
        ms.short_interest_pct = ctx.short_interest_pct
        ms.sector = ctx.sector
        ms.sector_is_leader = ctx.sector_is_leader
        ms.sue = ctx.sue
        ms.rs_rank_pct = ctx.rs_rank_pct
        ms.guidance_raised = ctx.guidance_raised
        ms.mom_20d = ctx.mom_20d
        ms.high_20d = ctx.high_20d
        ms.rsi2 = ctx.rsi2
        if ctx.sma50 is not None:
            ms.sma50 = ctx.sma50
        if ctx.sma200 is not None:
            ms.sma200 = ctx.sma200
        return ms

    def build_watchlist(self, tickers: List[str], now_et: str,
                        data: Dict[str, dict], regime: str) -> Dict[str, MarketState]:
        """data[ticker] = {quote, bars_by_tf, ctx, bid, ask}. Returns states for
        names with usable data; silently skips degraded names."""
        out: Dict[str, MarketState] = {}
        for t in tickers:
            d = data.get(t)
            if not d or not d.get("bars_by_tf"):
                continue
            out[t] = self.build(t, now_et, d["quote"], d["bars_by_tf"], regime,
                                ctx=d.get("ctx"), bid=d.get("bid", 0.0),
                                ask=d.get("ask", 0.0))
        return out
