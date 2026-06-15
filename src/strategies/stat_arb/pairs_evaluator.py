"""
HOOD DaBang — Pairs evaluator (Brief §8 #19).

Standalone evaluation of cointegrated pairs, kept SEPARATE from the single-name
controller on purpose: two-legged market-neutral trades need a "both legs or
neither" execution protocol distinct from the single-position atomic-entry path,
and that protocol can only be fully proven against the live broker. This module
produces the trade DECISIONS (which pairs, which direction, sizing, exit) so the
logic is complete and tested; live two-legged execution wiring is an operator
checkpoint like §34 MCP discovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .pairs import PairsStatArb, rolling_zscore, hedge_ratio


@dataclass
class PairDecision:
    pair: Tuple[str, str]
    action: str                  # "enter" | "exit" | "hold"
    z: float
    long_leg: Optional[str] = None
    short_leg: Optional[str] = None
    reason: str = ""


@dataclass
class OpenPair:
    a: str
    b: str
    entry_z: float
    long_leg: str
    short_leg: str


class PairsEvaluator:
    def __init__(self, strategy: Optional[PairsStatArb] = None):
        self.s = strategy or PairsStatArb()
        self.open: Dict[str, OpenPair] = {}      # key "A/B"

    @staticmethod
    def _key(a: str, b: str) -> str:
        return f"{a}/{b}"

    def evaluate(self, a: str, b: str, prices_a: Sequence[float],
                 prices_b: Sequence[float], regime: str = "crisis") -> PairDecision:
        beta = hedge_ratio(prices_a, prices_b)
        spread = [pa - beta * pb for pa, pb in zip(prices_a, prices_b)]
        z = rolling_zscore(spread)
        key = self._key(a, b)
        if z is None:
            # z is undefined either from too little data OR a fully converged
            # (zero-variance) spread. For an OPEN pair with enough data, a
            # converged spread is the ultimate reversion -> exit.
            if key in self.open and len(spread) >= 20:
                op = self.open.pop(key)
                return PairDecision((a, b), "exit", 0.0, op.long_leg, op.short_leg,
                                    "spread_reverted")
            return PairDecision((a, b), "hold", 0.0, reason="insufficient_data")

        # manage an existing pair position
        if key in self.open:
            exit_reason = self.s.should_exit_pair(z)
            if exit_reason:
                op = self.open.pop(key)
                return PairDecision((a, b), "exit", round(z, 3), op.long_leg,
                                    op.short_leg, exit_reason)
            return PairDecision((a, b), "hold", round(z, 3),
                                reason="spread_not_reverted")

        # consider a new entry
        if abs(z) >= self.s.entry_z:
            if z > 0:                            # a rich -> short a, long b
                long_leg, short_leg = b, a
            else:
                long_leg, short_leg = a, b
            self.open[key] = OpenPair(a, b, round(z, 3), long_leg, short_leg)
            return PairDecision((a, b), "enter", round(z, 3), long_leg, short_leg,
                                f"|z|={abs(z):.2f}>=entry")
        return PairDecision((a, b), "hold", round(z, 3), reason="z_below_entry")
