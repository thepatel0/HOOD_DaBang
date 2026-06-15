"""
HOOD DaBang — Monte-Carlo account simulator & ruin analysis.

Answers the operator's "what could be the impact of this decision?" with a
*distribution* rather than a guess. Given a strategy's edge (win rate, payoff)
and a per-trade risk fraction, it simulates thousands of compounding account
paths and reports terminal-wealth percentiles, median log-growth, AND the
probability of ruin (hitting the catastrophic floor).

`optimal_risk_fraction` sweeps the risk fraction and returns the one that
maximises geometric growth SUBJECT TO a ruin-probability ceiling — i.e. the
Kelly-optimal bet, bounded by survival. This is how risk becomes a *reasoned
variable* instead of a hardcoded constant.

Pure stdlib (random + statistics). Reusable $0 daily/weekly script.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SimSummary:
    risk_fraction: float
    n_paths: int
    n_trades: int
    median_terminal: float
    mean_terminal: float
    p5_terminal: float
    p95_terminal: float
    prob_ruin: float           # fraction of paths that hit the catastrophic floor
    prob_profit: float         # fraction ending above start
    median_log_growth: float   # per-path mean log return (geometric growth proxy)
    median_max_drawdown: float


def kelly_full_fraction(p: float, win_R: float, loss_R: float = 1.0) -> float:
    """Analytic growth-optimal risk fraction for asymmetric R payoffs:
        f* = (p*win_R - q*loss_R) / (win_R*loss_R),  q = 1-p.
    Returns 0 if the edge is non-positive (never bet a losing game)."""
    q = 1.0 - p
    f = (p * win_R - q * loss_R) / (win_R * loss_R)
    return max(0.0, f)


def simulate(p: float, win_R: float, loss_R: float, risk_fraction: float,
             *, n_trades: int = 200, n_paths: int = 2000,
             start_equity: float = 1500.0, catastrophic_floor: float = 1050.0,
             seed: int = 7) -> SimSummary:
    """Simulate compounding paths. Each trade risks `risk_fraction` of CURRENT
    equity (so 1R loss scales with the account). A path is 'ruined' the first
    time equity touches the catastrophic floor (and stops trading thereafter)."""
    rng = random.Random(seed)
    terminals: List[float] = []
    ruined = 0
    profit = 0
    log_growths: List[float] = []
    max_dds: List[float] = []

    for _ in range(n_paths):
        eq = start_equity
        peak = eq
        max_dd = 0.0
        path_ruined = False
        for _ in range(n_trades):
            if eq <= catastrophic_floor:
                path_ruined = True
                break
            r1 = risk_fraction * eq  # 1R in dollars, compounding
            if rng.random() < p:
                eq += win_R * r1
            else:
                eq -= loss_R * r1
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        if path_ruined or eq <= catastrophic_floor:
            ruined += 1
        if eq > start_equity:
            profit += 1
        terminals.append(eq)
        max_dds.append(max_dd)
        # mean per-trade log growth (guard against non-positive equity)
        if eq > 0:
            log_growths.append(math.log(eq / start_equity) / n_trades)

    terminals.sort()

    def pct(xs, q):
        return xs[min(len(xs) - 1, max(0, int(q * len(xs))))]

    return SimSummary(
        risk_fraction=risk_fraction,
        n_paths=n_paths, n_trades=n_trades,
        median_terminal=round(statistics.median(terminals), 2),
        mean_terminal=round(statistics.fmean(terminals), 2),
        p5_terminal=round(pct(terminals, 0.05), 2),
        p95_terminal=round(pct(terminals, 0.95), 2),
        prob_ruin=round(ruined / n_paths, 4),
        prob_profit=round(profit / n_paths, 4),
        median_log_growth=round(statistics.median(log_growths), 6) if log_growths else -9.9,
        median_max_drawdown=round(statistics.median(max_dds), 4),
    )


@dataclass
class RiskRecommendation:
    recommended_fraction: float
    kelly_full: float
    ruin_tolerance: float
    rationale: str
    sweep: List[SimSummary] = field(default_factory=list)


def optimal_risk_fraction(
    p: float, win_R: float, loss_R: float = 1.0, *,
    ruin_tolerance: float = 0.01,
    grid: List[float] = None,
    hard_cap: float = 0.025,
    n_trades: int = 200, n_paths: int = 2000,
    start_equity: float = 1500.0, catastrophic_floor: float = 1050.0,
) -> RiskRecommendation:
    """Sweep risk fractions; pick the one maximising median terminal wealth
    subject to prob_ruin <= ruin_tolerance and fraction <= hard_cap.

    This operationalises the operator's instruction: risk is a variable we
    OPTIMISE, but bounded by a survival constraint that cannot be traded away."""
    if grid is None:
        grid = [round(x, 4) for x in
                [0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]]
    kelly = kelly_full_fraction(p, win_R, loss_R)

    sweep = [simulate(p, win_R, loss_R, f, n_trades=n_trades, n_paths=n_paths,
                      start_equity=start_equity, catastrophic_floor=catastrophic_floor)
             for f in grid if f <= max(grid)]

    # candidates that respect the survival constraint and the absolute hard cap
    viable = [s for s in sweep
              if s.prob_ruin <= ruin_tolerance and s.risk_fraction <= hard_cap]
    if viable:
        best = max(viable, key=lambda s: s.median_terminal)
        rationale = (f"Among fractions with P(ruin)<={ruin_tolerance} and f<={hard_cap}, "
                     f"f={best.risk_fraction} maximises median terminal "
                     f"(${best.median_terminal}); full-Kelly={kelly:.4f} "
                     f"(half-Kelly={kelly/2:.4f}).")
        rec = best.risk_fraction
    else:
        # nothing clears the ruin bar -> fall to the smallest fraction (survive)
        best = min(sweep, key=lambda s: s.risk_fraction)
        rationale = (f"No fraction met P(ruin)<={ruin_tolerance}; defaulting to the "
                     f"smallest f={best.risk_fraction} to prioritise survival. "
                     f"Edge may be too weak to size up.")
        rec = best.risk_fraction

    return RiskRecommendation(
        recommended_fraction=rec, kelly_full=round(kelly, 4),
        ruin_tolerance=ruin_tolerance, rationale=rationale, sweep=sweep)
