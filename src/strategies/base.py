"""
HOOD DaBang — Strategy framework (Brief §8, §30.1).

A Strategy is a pure-logic object: given a MarketState (already populated with
Tier-0 indicators by the analysts), it proposes Setups and manages open
positions. Strategies contain NO data fetching and NO LLM calls — they are
deterministic, $0, and identical in backtest and live (parity principle).

The MarketState is the single contract between the (numpy-heavy) Tier-0 analysts
and the (pure-logic) strategies, so strategies stay testable with hand-built
fixtures and never depend on a live feed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------- #
# Market data contracts                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Bar:
    ts: str          # ISO 8601 with tz
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class MarketState:
    """Everything a strategy needs to decide, precomputed by Tier-0 analysts.
    Strategies READ this; they never compute indicators that require external
    data. Optional fields are None when the relevant analyst is degraded."""
    ticker: str
    now_et: str                              # ISO timestamp, US/Eastern
    quote: float                             # last/mid price
    bid: float = 0.0
    ask: float = 0.0
    spread_pct: float = 0.0
    bars: Dict[str, List[Bar]] = field(default_factory=dict)   # "1m","5m","15m","1H","1D"
    # session levels
    vwap: Optional[float] = None
    prior_close: Optional[float] = None
    prior_high: Optional[float] = None
    prior_low: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    opening_range_high: Optional[float] = None
    opening_range_low: Optional[float] = None
    # indicators
    atr_1m: Optional[float] = None
    atr_14: Optional[float] = None
    rvol: Optional[float] = None             # relative volume vs time-of-day avg
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    rsi14: Optional[float] = None
    bb_width_pctile: Optional[float] = None  # 0..1 percentile of trailing width
    # context
    regime: str = "range_low_vol"
    has_catalyst: bool = False
    catalyst_age_min: Optional[float] = None
    catalyst_sources: int = 0
    gap_pct: Optional[float] = None          # (open - prior_close)/prior_close
    adv_shares: Optional[float] = None
    rsi2: Optional[float] = None             # fast RSI for mean-reversion swings
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    # strategy-specific context (populated by analysts/feeds; None => strategy abstains)
    short_interest_pct: Optional[float] = None   # % of float short
    days_since_earnings: Optional[int] = None
    is_earnings_today: bool = False
    sue: Optional[float] = None                  # standardized unexpected earnings
    rs_rank_pct: Optional[float] = None          # relative-strength rank in sector 0..1
    guidance_raised: Optional[bool] = None
    sector: Optional[str] = None
    sector_is_leader: bool = False               # this name's sector leads today
    mom_20d: Optional[float] = None              # 20-day price momentum
    high_20d: Optional[float] = None             # 20-day high
    # freshness (Brief 30.4)
    quote_age_ms: int = 0
    last_bar_age_s: int = 0

    def last(self, tf: str) -> Optional[Bar]:
        b = self.bars.get(tf)
        return b[-1] if b else None


# --------------------------------------------------------------------------- #
# Setup (a proposed trade) and Action (managing an open trade)                 #
# --------------------------------------------------------------------------- #
@dataclass
class Setup:
    """A strategy's proposed entry, carrying the 8 conviction factors it can
    self-assess deterministically. The Conviction Gate consumes these."""
    ticker: str
    strategy: str
    version: str
    side: str                                # "long" | "short"
    entry_price: float
    stop_price: float
    targets: List[Tuple[float, float]] = field(default_factory=list)  # (price, frac)
    factors: Dict[str, float] = field(default_factory=dict)           # 8 conviction factors
    requires_catalyst: bool = False
    expected_hold_min: int = 60
    notes: str = ""

    @property
    def per_share_risk(self) -> float:
        return abs(self.entry_price - self.stop_price)

    @property
    def reward_risk(self) -> float:
        if not self.targets or self.per_share_risk <= 0:
            return 0.0
        t1 = self.targets[0][0]
        return abs(t1 - self.entry_price) / self.per_share_risk


class ActionType(Enum):
    HOLD = "hold"
    MOVE_STOP = "move_stop"        # e.g. to break-even / trail
    SCALE_OUT = "scale_out"        # take partial at target
    EXIT = "exit"                  # full close (target/time/invalidation)


@dataclass
class Action:
    type: ActionType
    reason: str = ""
    new_stop: Optional[float] = None
    fraction: float = 1.0          # for SCALE_OUT/EXIT


@dataclass
class Position:
    ticker: str
    side: str
    shares: int
    entry_price: float
    stop_price: float
    targets: List[Tuple[float, float]]
    strategy: str
    opened_ts: str
    bars_held: int = 0


# --------------------------------------------------------------------------- #
# Wake conditions (Brief §30.1 signal routing)                                 #
# --------------------------------------------------------------------------- #
@dataclass
class WakeCondition:
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m"])
    requires_catalyst: bool = False
    min_rvol: float = 0.0
    session_windows: List[Tuple[str, str]] = field(default_factory=list)  # ("09:35","10:00")
    watch_tickers_only: bool = True

    def matches(self, ms: MarketState, timeframe: str) -> bool:
        if timeframe not in self.timeframes:
            return False
        if self.requires_catalyst and not ms.has_catalyst:
            return False
        if self.min_rvol > 0 and (ms.rvol is None or ms.rvol < self.min_rvol):
            return False
        if self.session_windows:
            t = ms.now_et[11:16] if len(ms.now_et) >= 16 else ms.now_et
            if not any(lo <= t <= hi for lo, hi in self.session_windows):
                return False
        return True


# --------------------------------------------------------------------------- #
# Strategy ABC                                                                 #
# --------------------------------------------------------------------------- #
ACTIVATION_STATES = ("development", "backtested", "paper", "live", "paused")


class Strategy(ABC):
    name: str = "base"
    version: str = "0.0.0"
    activation_status: str = "development"
    requires_llm_gating: bool = True
    regime_preferences: Dict[str, float] = {}
    wake: WakeCondition = WakeCondition()

    @abstractmethod
    def scan(self, ms: MarketState) -> List[Setup]:
        """Return zero or more Setups visible in this MarketState."""
        raise NotImplementedError

    @abstractmethod
    def manage(self, pos: Position, ms: MarketState) -> Action:
        """Decide what to do with an open position."""
        raise NotImplementedError

    def regime_weight(self, regime: str) -> float:
        return self.regime_preferences.get(regime, 0.0)
