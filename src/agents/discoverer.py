"""
HOOD DaBang — Discoverer (Brief §5.2, §12).

Weekly: mines the journal (and missed_trades) for patterns — "when X, Y often
follows" — and emits HYPOTHESES, never live trades. Every hypothesis must go
through backtest + the five validation gates (it cannot propose real capital).
Deterministic mining core; the hypotheses feed the FalsificationEngine.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..decision.hypothesis import Hypothesis


@dataclass
class DiscoveredPattern:
    description: str
    segment: str                 # e.g. "orb@bull_trend_low_vol"
    n: int
    expectancy_r: float
    win_rate: float
    direction: str               # "promising" | "degrading"


class Discoverer:
    def __init__(self, llm_client=None, min_sample: int = 10):
        self.llm = llm_client
        self.min_sample = min_sample

    def mine(self, trades: List[dict]) -> List[DiscoveredPattern]:
        """trades: dicts with strategy, market_regime (or regime), pnl_r."""
        buckets: Dict[str, List[float]] = defaultdict(list)
        for t in trades:
            regime = t.get("market_regime") or t.get("regime") or "unknown"
            key = f"{t.get('strategy','?')}@{regime}"
            buckets[key].append(t.get("pnl_r", 0.0))

        patterns: List[DiscoveredPattern] = []
        for seg, rs in buckets.items():
            if len(rs) < self.min_sample:
                continue
            exp = sum(rs) / len(rs)
            wr = sum(1 for r in rs if r > 0) / len(rs)
            direction = "promising" if exp > 0.1 else ("degrading" if exp < -0.1 else "neutral")
            if direction == "neutral":
                continue
            strat, regime = seg.split("@", 1)
            verb = "outperforms" if direction == "promising" else "underperforms"
            patterns.append(DiscoveredPattern(
                description=f"{strat} {verb} in {regime} (exp {exp:+.2f}R over {len(rs)})",
                segment=seg, n=len(rs), expectancy_r=round(exp, 3),
                win_rate=round(wr, 3), direction=direction))
        return patterns

    def to_hypotheses(self, patterns: List[DiscoveredPattern]) -> List[Hypothesis]:
        out: List[Hypothesis] = []
        for p in patterns:
            if p.direction == "promising":
                out.append(Hypothesis(
                    id=f"discover:{p.segment}",
                    statement=f"Increasing allocation to {p.segment} raises expectancy",
                    null_statement=f"{p.segment} has no positive edge vs baseline",
                    direction="greater", min_sample=self.min_sample))
            else:
                out.append(Hypothesis(
                    id=f"discover:{p.segment}",
                    statement=f"{p.segment} should be paused/reduced",
                    null_statement=f"{p.segment} edge is unchanged",
                    direction="less", min_sample=self.min_sample))
        return out
