"""
HOOD DaBang — Meta-Learner (Brief §5.2, §12, Tier 3 Opus weekly).

Orchestrates self-improvement around the bedrock: for each agent, evaluate on the
golden set (judge), and if it regressed below its baseline, request prompt
revisions, evaluate them via the MetaPrompter (FalsificationEngine + cost
criterion), and queue a winner to SHADOW before any promotion. Cannot modify
risk/killswitch/reconciliation/tests/gate-floors (recursive constraint, enforced
by the MetaPrompter's guard).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..self_improvement.golden import GoldenSet, judge, accuracy
from ..self_improvement.shadow import MetaPrompter, PromptCandidate, MetaDecision


@dataclass
class AgentEval:
    agent: str
    accuracy: float
    baseline: float
    regressed: bool


@dataclass
class MetaReport:
    evals: List[AgentEval] = field(default_factory=list)
    promotions_to_shadow: List[str] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)
    notes: str = ""


class MetaLearner:
    def __init__(self, regression_margin: float = 0.10):
        self.mp = MetaPrompter()
        self.margin = regression_margin       # below baseline*(1-margin) == regressed

    def evaluate_agent(self, agent: str, golden: GoldenSet,
                       agent_fn: Callable, baseline: float) -> AgentEval:
        acc = accuracy(judge(golden, agent_fn))
        regressed = acc < baseline * (1 - self.margin)
        return AgentEval(agent, round(acc, 3), baseline, regressed)

    def consider_revision(self, ev: AgentEval, baseline_prompt: str,
                          candidate: PromptCandidate, baseline_scores: List[float],
                          candidate_scores: List[float]) -> MetaDecision:
        """A revision is only adopted (queued to shadow) if it beats baseline with
        statistical significance and clears the cost criterion AND targets a
        non-protected path."""
        return self.mp.evaluate(baseline_prompt, candidate, baseline_scores,
                                candidate_scores)

    def run(self, agents: Dict[str, Callable], golden: GoldenSet,
            baselines: Dict[str, float],
            revisions: Optional[Dict[str, tuple]] = None) -> MetaReport:
        """agents: {name: agent_fn}. revisions: {name: (baseline_prompt, candidate,
        baseline_scores, candidate_scores)} for regressed agents."""
        report = MetaReport()
        revisions = revisions or {}
        for name, fn in agents.items():
            ev = self.evaluate_agent(name, golden, fn, baselines.get(name, 0.9))
            report.evals.append(ev)
            if ev.regressed and name in revisions:
                bp, cand, bs, cs = revisions[name]
                d = self.consider_revision(ev, bp, cand, bs, cs)
                if d.adopt:
                    report.promotions_to_shadow.append(name)
                else:
                    report.rejected.append(f"{name}: {d.reason}")
        report.notes = (f"{len(report.evals)} agents evaluated, "
                        f"{len(report.promotions_to_shadow)} queued to shadow, "
                        f"{len(report.rejected)} revisions rejected.")
        return report
