"""
HOOD DaBang — the recursive constraint (Brief §12, failure mode #21).

The Meta-Learner improves the system AROUND the bedrock, never THROUGH it. This
guard is the structural enforcement: any self-modification targeting a protected
component is REJECTED (fail-closed), regardless of how good it looks on metrics.

Protected (immutable to self-improvement): risk gate, killswitches,
reconciliation, the test suite, strategy version locking, and the Conviction-Gate
hard floors.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# Paths/components the self-improvement loop may NEVER modify.
PROTECTED_PATTERNS = [
    r"(^|/)src/risk\.py$",
    r"(^|/)src/killswitch\.py$",
    r"(^|/)src/reconciliation\.py$",
    r"(^|/)src/conviction/(gate|thresholds)\.py$",
    r"(^|/)tests/",
    r"(^|/)src/strategies/registry\.py$",     # strategy version locking
    r"PERMITTED_VERSIONS\.lock$",
]

# Config keys the self-improvement loop may never change.
PROTECTED_CONFIG_KEYS = {
    "risk", "conviction.stage1_hard_floor", "conviction.execution_floor",
    "conviction.floor_min", "conviction.floor_max", "adaptive_risk.absolute_max_pct",
    "llm.daily_budget_usd", "llm.monthly_budget_usd",
    "catastrophic_halt_equity_usd",
}


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""


_compiled = [re.compile(p) for p in PROTECTED_PATTERNS]


def can_modify_path(path: str) -> GuardResult:
    for rx in _compiled:
        if rx.search(path):
            return GuardResult(False, f"protected path: {path} (recursive constraint)")
    return GuardResult(True, "ok")


def can_modify_config_key(dotted_key: str) -> GuardResult:
    # block exact protected keys and any child of a protected section
    for protected in PROTECTED_CONFIG_KEYS:
        if dotted_key == protected or dotted_key.startswith(protected + "."):
            return GuardResult(False, f"protected config key: {dotted_key}")
    return GuardResult(True, "ok")


def assert_allowed_path(path: str) -> None:
    g = can_modify_path(path)
    if not g.allowed:
        raise PermissionError(g.reason)
