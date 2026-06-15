"""
HOOD DaBang — shadow mode + meta-prompter (Brief §12, the Knight Capital defense).

A new prompt/strategy version runs IN PARALLEL with live, consuming the same
inputs but emitting NO orders. Promote only if shadow >= live + threshold over the
window; discard if worse; extend on a tie. A new code path is never live without
first proving itself in parallel.

The MetaPrompter proposes revised prompts, scores them on the golden set, and
promotes via the FalsificationEngine (statistically significant, correct
direction). It respects the recursive constraint and the cost criterion (a 50%
longer prompt must show >50% improvement).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..decision.hypothesis import Hypothesis, FalsificationEngine
from .guard import can_modify_path, GuardResult


@dataclass
class ShadowComparison:
    live_samples: List[float] = field(default_factory=list)
    shadow_samples: List[float] = field(default_factory=list)

    def record(self, live_metric: float, shadow_metric: float) -> None:
        self.live_samples.append(live_metric)
        self.shadow_samples.append(shadow_metric)

    def decide(self, threshold: float = 0.0, min_n: int = 5) -> str:
        n = min(len(self.live_samples), len(self.shadow_samples))
        if n < min_n:
            return "extend"
        live = sum(self.live_samples) / len(self.live_samples)
        shadow = sum(self.shadow_samples) / len(self.shadow_samples)
        if shadow >= live + threshold + 1e-9:
            return "promote"
        if shadow < live - 1e-9:
            return "discard"
        return "extend"


@dataclass
class PromptCandidate:
    name: str
    prompt: str
    target_path: str = "src/agents/intel.py"   # what file it would change


@dataclass
class MetaDecision:
    candidate: str
    adopt: bool
    reason: str


class MetaPrompter:
    def __init__(self, alpha: float = 0.05, min_sample: int = 30):
        self.engine = FalsificationEngine()
        self.alpha = alpha
        self.min_sample = min_sample

    def evaluate(self, baseline_prompt: str, candidate: PromptCandidate,
                 baseline_scores: List[float], candidate_scores: List[float]
                 ) -> MetaDecision:
        # recursive constraint first (fail-closed)
        g: GuardResult = can_modify_path(candidate.target_path)
        if not g.allowed:
            return MetaDecision(candidate.name, False, g.reason)

        # cost criterion: a much longer prompt must clear a higher bar
        len_ratio = len(candidate.prompt) / max(1, len(baseline_prompt))
        h = Hypothesis(
            id=f"meta:{candidate.name}",
            statement="candidate prompt beats baseline on golden samples",
            null_statement="candidate is no better than baseline",
            direction="greater", alpha=self.alpha, min_sample=self.min_sample)
        res = self.engine.evaluate(h, candidate_scores, baseline_scores)
        if not res.adopt:
            return MetaDecision(candidate.name, False,
                                f"not significantly better ({res.reason})")
        if len_ratio > 1.5:
            # require >50% improvement in mean to justify >50% longer prompt
            base_mean = sum(baseline_scores) / len(baseline_scores)
            cand_mean = sum(candidate_scores) / len(candidate_scores)
            if base_mean <= 0 or (cand_mean - base_mean) / abs(base_mean) < 0.5:
                return MetaDecision(candidate.name, False,
                                    "longer prompt without >50% improvement (cost)")
        return MetaDecision(candidate.name, True,
                            f"adopt: significant improvement ({res.effect_size:+.3f})")
