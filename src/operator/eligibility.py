"""
HOOD DaBang — live-trading eligibility (Brief §35 Definition of Done).

The ControlPlane calls this before arming/enabling live trading. Returns
(eligible, blockers). Live is allowed only when the survival preconditions are
met — not just because the operator wants it. This is the guardrail that makes
"trading on" safe to expose as a simple command.
"""
from __future__ import annotations

from typing import List, Tuple

from ..strategies.registry import StrategyRegistry, FIVE_GATES


def live_eligibility(registry: StrategyRegistry, *, paper_trades: int = 0,
                     paper_expectancy_r: float = 0.0,
                     self_tests_green: bool = True,
                     dod_overrides: bool = False) -> Tuple[bool, List[str]]:
    """Eligible only if: >=1 strategy cleared all five validation gates, the paper
    forward period shows positive expectancy over >=30 trades, and self-tests are
    green. `dod_overrides` lets the operator acknowledge the remaining manual DoD
    items after reviewing them."""
    blockers: List[str] = []

    gate_passers = [rs.strategy.name for rs in registry.all()
                    if rs.validation.all_passed()]
    if not gate_passers:
        blockers.append("no strategy has passed all five validation gates")

    live_strategies = [s.name for s in registry.live_strategies()]
    if not live_strategies and not gate_passers:
        blockers.append("no strategy is promoted to 'live'")

    if paper_trades < 30:
        blockers.append(f"paper forward period too short ({paper_trades}/30 trades)")
    elif paper_expectancy_r <= 0:
        blockers.append(f"paper expectancy non-positive ({paper_expectancy_r:+.2f}R)")

    if not self_tests_green:
        blockers.append("self-tests not green")

    if not dod_overrides:
        blockers.append("operator has not acknowledged the 12-point Definition of "
                        "Done (§35) — review then pass dod_overrides=True")

    return (len(blockers) == 0, blockers)
