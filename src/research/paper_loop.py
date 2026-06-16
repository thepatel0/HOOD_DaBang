"""
HOOD DaBang — paper learning loop (Brief §12 self-improvement, isolated).

Runs in the PAPER environment (isolated data). Continuously learns from paper
decision-making to improve accuracy: mines paper trades for patterns, VALIDATES
them via falsification, and graduates survivors to the shared KnowledgeBase.
Also runs A/B tests between strategy variants on paper data.

Nothing here touches production data — it reads the paper journal and writes only
validated knowledge (with source='paper') to the shared store.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..agents.discoverer import Discoverer
from ..knowledge.base import KnowledgeBase, KnowledgePattern
from ..decision.hypothesis import Hypothesis, FalsificationEngine


@dataclass
class LearningReport:
    n_paper_trades: int
    patterns_examined: int
    patterns_validated: int
    validated: List[KnowledgePattern] = field(default_factory=list)
    notes: str = ""


@dataclass
class ABResult:
    winner: Optional[str]
    adopt: bool
    p_value: float
    effect: float
    reason: str


class PaperLearningLoop:
    def __init__(self, paper_journal, knowledge: KnowledgeBase,
                 discoverer: Optional[Discoverer] = None, min_sample: int = 30):
        self.journal = paper_journal       # PAPER env journal (isolated)
        self.knowledge = knowledge
        self.discoverer = discoverer or Discoverer(min_sample=10)
        self.min_sample = min_sample
        self.engine = FalsificationEngine()

    def _paper_trades(self) -> List[dict]:
        rows = self.journal.conn.execute(
            "SELECT strategy, market_regime, pnl_r FROM trades "
            "WHERE exit_ts IS NOT NULL").fetchall()
        return [{"strategy": r[0], "market_regime": r[1], "pnl_r": r[2] or 0.0}
                for r in rows]

    def learn(self) -> LearningReport:
        trades = self._paper_trades()
        baseline = [t["pnl_r"] for t in trades]
        # group by strategy@regime
        seg: Dict[str, List[float]] = defaultdict(list)
        for t in trades:
            seg[f"{t['strategy']}@{t['market_regime']}"].append(t["pnl_r"])

        validated: List[KnowledgePattern] = []
        examined = 0
        for segment, rs in seg.items():
            if len(rs) < self.min_sample:
                continue
            examined += 1
            # treatment = this segment; control = the overall baseline
            kp = self.knowledge.validate_and_store(
                segment, f"{segment} shows a real edge in paper",
                treatment_samples=rs, control_samples=baseline,
                source="paper", min_sample=self.min_sample)
            if kp is not None:
                validated.append(kp)

        return LearningReport(
            n_paper_trades=len(trades), patterns_examined=examined,
            patterns_validated=len(validated), validated=validated,
            notes=f"{len(validated)}/{examined} segments validated into knowledge "
                  f"from {len(trades)} paper trades.")

    def ab_test(self, name_a: str, results_a: List[float],
                name_b: str, results_b: List[float]) -> ABResult:
        """Compare two strategy variants on paper R-multiples. Adopts B over A only
        if B beats A with significance (else keep A — burden on the challenger)."""
        h = Hypothesis(id=f"ab:{name_b}_vs_{name_a}",
                       statement=f"{name_b} beats {name_a}",
                       null_statement="no difference", direction="greater",
                       min_sample=self.min_sample)
        res = self.engine.evaluate(h, results_b, results_a)
        winner = name_b if res.adopt else name_a
        return ABResult(winner=winner, adopt=res.adopt, p_value=res.p_value,
                        effect=res.effect_size, reason=res.reason)
