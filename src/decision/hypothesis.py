"""
HOOD DaBang — FALSIFICATION ENGINE (the operator's decision philosophy as code).

The operator's rule: "Start with the null hypothesis that your decision is WRONG,
then find a way to prove it wrong; only if you can, is it worth trying."

This is Popperian falsification applied to every consequential change — a new
strategy, a risk-parameter change, a prompt revision, a conviction-floor tweak.
A change is ADOPTED only if the data lets us reject the null ("the change does
nothing / makes things worse") at a chosen significance level, with a large
enough sample and an effect in the intended direction.

Pure stdlib: uses a permutation/bootstrap test (no scipy needed, and more robust
to non-normal trade returns than a t-test — which matters because trade P&L is
famously fat-tailed). This mirrors the brief's bootstrap-PBO and the Meta-Learner
promotion rule (p<0.05, n>=30).
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Hypothesis:
    """A proposed change, framed so it can be falsified."""
    id: str
    statement: str                 # "Raising per-trade risk to 2% increases growth"
    null_statement: str            # "...does NOT increase growth (or harms it)"
    direction: str = "greater"     # treatment expected 'greater' or 'less' than control
    alpha: float = 0.05            # reject null if p < alpha
    min_sample: int = 30           # need enough evidence (brief: n>=30)


@dataclass
class TestResult:
    hypothesis_id: str
    p_value: float
    reject_null: bool
    adopt: bool                    # reject_null AND direction correct AND n sufficient
    effect_size: float             # mean(treatment) - mean(control)
    n_treatment: int
    n_control: int
    reason: str
    ci95: Optional[tuple] = None   # bootstrap 95% CI of the effect


def _mean(xs: List[float]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def permutation_test(treatment: List[float], control: List[float],
                     direction: str = "greater", n_perm: int = 10000,
                     seed: int = 1234) -> tuple:
    """One-sided permutation test on the difference of means.
    Returns (p_value, observed_effect). The null is 'the labels don't matter'
    (i.e. the change has no effect)."""
    rng = random.Random(seed)
    obs = _mean(treatment) - _mean(control)
    pooled = treatment + control
    n_t = len(treatment)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        diff = _mean(pooled[:n_t]) - _mean(pooled[n_t:])
        if direction == "greater":
            if diff >= obs:
                count += 1
        else:  # 'less'
            if diff <= obs:
                count += 1
    # +1 smoothing so p is never exactly 0 (we never claim certainty)
    p = (count + 1) / (n_perm + 1)
    return p, obs


def bootstrap_ci(treatment: List[float], control: List[float],
                 n_boot: int = 5000, seed: int = 99) -> tuple:
    """95% bootstrap CI for mean(treatment) - mean(control)."""
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        t = [treatment[rng.randrange(len(treatment))] for _ in treatment]
        c = [control[rng.randrange(len(control))] for _ in control]
        diffs.append(_mean(t) - _mean(c))
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[int(0.975 * len(diffs))]
    return (round(lo, 6), round(hi, 6))


class FalsificationEngine:
    """Adjudicates whether a hypothesised change survives its null. The default
    stance is REJECT the change (fail-closed): the burden of proof is on the
    change, exactly as the operator framed it."""

    def evaluate(self, h: Hypothesis, treatment: List[float],
                 control: List[float], n_perm: int = 10000) -> TestResult:
        n_t, n_c = len(treatment), len(control)

        # Not enough evidence -> do NOT adopt (null stands by default).
        if n_t < h.min_sample or n_c < h.min_sample:
            return TestResult(
                h.id, p_value=1.0, reject_null=False, adopt=False,
                effect_size=_mean(treatment) - _mean(control),
                n_treatment=n_t, n_control=n_c,
                reason=f"insufficient_sample (need >= {h.min_sample} each)")

        p, effect = permutation_test(treatment, control, h.direction, n_perm)
        ci = bootstrap_ci(treatment, control)
        reject = p < h.alpha
        # direction sanity: the effect must point the way the hypothesis claims
        dir_ok = (effect > 0) if h.direction == "greater" else (effect < 0)
        adopt = reject and dir_ok

        if adopt:
            reason = f"null_rejected p={p:.4f}<{h.alpha}; effect={effect:+.4f}; ADOPT"
        elif reject and not dir_ok:
            reason = f"significant but WRONG direction (effect={effect:+.4f}); reject change"
        else:
            reason = f"null_not_rejected p={p:.4f}>=alpha; change unproven; reject"

        return TestResult(h.id, p, reject, adopt, effect, n_t, n_c, reason, ci)
