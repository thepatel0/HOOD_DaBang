"""
HOOD DaBang — Strategy registry (Brief §8, §9, §13, §30.1).

Tracks each strategy's activation status and the FIVE validation-gate flags, and
REFUSES to promote a strategy to `live` unless all five are set. This is the
mechanical enforcement of "distrust every backtest" — the registry is the single
choke point between a backtest that looked good and real capital.

Also holds the regime-conditioned allocation matrix and the §30.1 signal router
(an inverted index so a bar-close only wakes the strategies whose conditions it
could satisfy — not all 19).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .base import Strategy, MarketState, Setup


# The five gates (Brief §9), in order.
FIVE_GATES = ("walkforward", "bootstrap_pbo", "deflated_sharpe", "oos", "paper")


@dataclass
class ValidationState:
    walkforward: bool = False
    bootstrap_pbo: bool = False
    deflated_sharpe: bool = False
    oos: bool = False
    paper: bool = False

    def all_passed(self) -> bool:
        return all(getattr(self, g) for g in FIVE_GATES)

    def missing(self) -> List[str]:
        return [g for g in FIVE_GATES if not getattr(self, g)]


class PromotionError(RuntimeError):
    """Raised when something tries to go live without clearing all five gates."""


@dataclass
class RegisteredStrategy:
    strategy: Strategy
    validation: ValidationState = field(default_factory=ValidationState)


class StrategyRegistry:
    def __init__(self, regime_allocations: Optional[Dict[str, Dict[str, float]]] = None):
        self._strategies: Dict[str, RegisteredStrategy] = {}
        # regime_allocations[regime][strategy_name] = weight
        self.regime_allocations = regime_allocations or {}

    # ----- registration -------------------------------------------------- #
    def register(self, strategy: Strategy) -> None:
        self._strategies[strategy.name] = RegisteredStrategy(strategy)

    def get(self, name: str) -> RegisteredStrategy:
        return self._strategies[name]

    def all(self) -> List[RegisteredStrategy]:
        return list(self._strategies.values())

    # ----- the five-gate lock -------------------------------------------- #
    def set_gate(self, name: str, gate: str, passed: bool = True) -> None:
        if gate not in FIVE_GATES:
            raise ValueError(f"unknown gate {gate!r}; must be one of {FIVE_GATES}")
        setattr(self._strategies[name].validation, gate, passed)

    def promote(self, name: str, status: str) -> None:
        """Move a strategy's activation status. Promotion to 'live' is BLOCKED
        unless all five validation gates have passed (fail-closed)."""
        rs = self._strategies[name]
        if status == "live" and not rs.validation.all_passed():
            raise PromotionError(
                f"{name} cannot go live; missing gates: {rs.validation.missing()}")
        rs.strategy.activation_status = status

    def live_strategies(self) -> List[Strategy]:
        return [rs.strategy for rs in self._strategies.values()
                if rs.strategy.activation_status == "live"]

    def tradeable(self) -> List[Strategy]:
        """Strategies allowed to propose real setups: live, or paper (sim only)."""
        return [rs.strategy for rs in self._strategies.values()
                if rs.strategy.activation_status in ("live", "paper")]

    # ----- regime-conditioned allocation --------------------------------- #
    def allocation(self, regime: str, strategy_name: str) -> float:
        return self.regime_allocations.get(regime, {}).get(strategy_name, 0.0)

    # ----- §30.1 signal routing ------------------------------------------ #
    def wake_strategies(self, ms: MarketState, timeframe: str) -> List[Strategy]:
        """Return only the tradeable strategies whose wake conditions match this
        bar-close, AND whose regime weight is > 0 in the current regime."""
        out = []
        for s in self.tradeable():
            if s.regime_weight(ms.regime) <= 0:
                continue
            if s.wake.matches(ms, timeframe):
                out.append(s)
        return out

    def scan_awake(self, ms: MarketState, timeframe: str) -> List[Setup]:
        """Wake matching strategies and collect their setups for this state."""
        setups: List[Setup] = []
        for s in self.wake_strategies(ms, timeframe):
            setups.extend(s.scan(ms))
        return setups
