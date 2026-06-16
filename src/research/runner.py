"""
HOOD DaBang — research runner: real-world data -> decisions (Brief §16).

The documented ingestion pipeline. Per cycle:
  1. Detect the market REGIME from real index data (SPY trend/vol + VIX + breadth).
  2. For each watchlist name, INGEST in detailed steps:
       a. price/volume bars (cached feed)
       b. news headlines -> deterministic catalyst classification ($0)
       c. earnings / short-interest / sector context (feeds, when wired)
       d. Tier-0 analytics (technical + microstructure) via the research pipeline
  3. Assemble a fully-typed MarketState per name.
  4. Run the decision engine (controller) — in RECOMMEND mode it writes
     recommendations to the journal + memory; in PAPER/LIVE it routes to execution.

Feeds are injected so this runs offline in tests and against real yfinance/RSS
in production. Deterministic and $0 except the optional Haiku news upgrade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..strategies.base import Bar, MarketState
from ..research.pipeline import ResearchPipeline, TickerContext
from ..research.news_classifier import aggregate as classify_news
from ..research.regime_features import detect_regime


@dataclass
class ResearchSummary:
    regime: str
    names_screened: int
    states_built: int
    recommendations: int
    notes: str = ""


class ResearchRunner:
    def __init__(self, bar_feed, controller, *, news_feed=None, regime_classifier=None,
                 pipeline: Optional[ResearchPipeline] = None,
                 context_provider: Optional[Callable[[str], TickerContext]] = None):
        self.bar_feed = bar_feed
        self.controller = controller
        self.news_feed = news_feed
        self.regime_classifier = regime_classifier
        self.pipeline = pipeline or ResearchPipeline()
        self.context_provider = context_provider

    # ----- step 1: regime ------------------------------------------------ #
    def detect_regime(self, vix: float = 18.0, breadth: float = 0.5) -> str:
        res = self.bar_feed.get_bars("SPY", interval="1d", lookback_days=250)
        if not res.bars or len(res.bars) < 50:
            return "transitional"
        return detect_regime(res.bars, vix=vix, breadth=breadth,
                             classifier=self.regime_classifier)

    # ----- step 2-3: ingest + build state per name ----------------------- #
    def build_state(self, ticker: str, now_et: str, regime: str,
                    interval: str = "5m") -> Optional[MarketState]:
        res = self.bar_feed.get_bars(ticker, interval=interval, lookback_days=5)
        bars = res.bars
        if not bars or len(bars) < 30:
            res = self.bar_feed.get_bars(ticker, interval="1d", lookback_days=60)
            bars = res.bars
            interval = "1d"
        if not bars or len(bars) < 30:
            return None

        ctx = self.context_provider(ticker) if self.context_provider else TickerContext()
        ctx.prior_close = bars[-2].c if len(bars) >= 2 else bars[-1].c

        # news -> deterministic catalyst context ($0)
        if self.news_feed is not None:
            news = self.news_feed.fetch(ticker, only_new=False)
            cat = classify_news([h.title for h in news.headlines])
            if cat.has_catalyst:
                ctx.has_catalyst = True
                ctx.catalyst_sources = cat.sources
                ctx.catalyst_age_min = 10   # RSS recency proxy

        return self.pipeline.build(ticker, now_et, bars[-1].c,
                                   {"1m": bars, "5m": bars}, regime, ctx=ctx)

    # ----- step 4: run the decision engine ------------------------------- #
    def run(self, watchlist: List[str], now_et: str, vix: float = 18.0,
            breadth: float = 0.5) -> ResearchSummary:
        regime = self.detect_regime(vix, breadth)
        states: Dict[str, MarketState] = {}
        for t in watchlist:
            ms = self.build_state(t, now_et, regime)
            if ms is not None:
                states[t] = ms
        recs_before = self.controller.recommendations_today
        trades_before = self.controller.state.trades_today if hasattr(
            self.controller, "state") and self.controller.state else 0
        if states:
            self.controller.process_tick(states, now_et)
        new_recs = self.controller.recommendations_today - recs_before
        return ResearchSummary(
            regime=regime, names_screened=len(watchlist), states_built=len(states),
            recommendations=new_recs,
            notes=f"regime={regime}; {len(states)}/{len(watchlist)} names had usable data")
