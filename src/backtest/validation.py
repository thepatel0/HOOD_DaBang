"""
HOOD DaBang — the five validation gates (Brief §9, §26.8).

A strategy may not trade real capital until it clears, in order:
  1. walk_forward          positive expectancy in >=70% of rolling validation windows
  2. bootstrap_overfit     overfit/fragility probability <= 0.05
  3. deflated_sharpe       DSR > 0 at 95% (Bailey & Lopez de Prado), trial-adjusted
  4. out_of_sample         OOS expectancy >= 50% of in-sample expectancy
  5. paper                 >=30 forward paper trades, positive expectancy (LIVE-only;
                           cannot be evaluated in backtest — marked pending here)

These return structured results the StrategyRegistry consumes to set its gate
flags. Pure math + reruns of the (no-look-ahead) backtest engine.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import List, Optional

from .engine import BacktestEngine


# --------------------------------------------------------------------------- #
# Moments                                                                      #
# --------------------------------------------------------------------------- #
def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def skewness(xs: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    m, sd = _mean(xs), _std(xs)
    if sd == 0:
        return 0.0
    return (n / ((n - 1) * (n - 2))) * sum(((x - m) / sd) ** 3 for x in xs)


def kurtosis(xs: List[float]) -> float:
    """Non-excess (Pearson) kurtosis; ~3 for a normal distribution."""
    n = len(xs)
    if n < 4:
        return 3.0
    m, sd = _mean(xs), _std(xs)
    if sd == 0:
        return 3.0
    return sum(((x - m) / sd) ** 4 for x in xs) / n


def per_trade_sharpe(r_series: List[float]) -> float:
    sd = _std(r_series)
    return (_mean(r_series) / sd) if sd > 0 else 0.0


# --------------------------------------------------------------------------- #
# Gate 3 — Deflated Sharpe Ratio                                               #
# --------------------------------------------------------------------------- #
def deflated_sharpe_ratio(r_series: List[float], n_trials: int = 10) -> float:
    """Probability the TRUE Sharpe > 0, deflated for the number of strategy
    variants tried and the non-normality of returns. Returns a probability in
    [0,1]; the gate passes if > 0.95."""
    T = len(r_series)
    if T < 5:
        return 0.0
    sr = per_trade_sharpe(r_series)
    sk = skewness(r_series)
    ku = kurtosis(r_series)
    N = NormalDist()
    emc = 0.5772156649015329  # Euler-Mascheroni
    n_trials = max(2, n_trials)
    # expected maximum Sharpe under the null across n_trials (variance of SR ~ 1/T)
    sr_trials_std = math.sqrt(1.0 / T)
    z1 = N.inv_cdf(1 - 1.0 / n_trials)
    z2 = N.inv_cdf(1 - 1.0 / (n_trials * math.e))
    sr0 = sr_trials_std * ((1 - emc) * z1 + emc * z2)
    denom = math.sqrt(max(1e-9, 1 - sk * sr + ((ku - 1) / 4.0) * sr ** 2))
    dsr = N.cdf(((sr - sr0) * math.sqrt(T - 1)) / denom)
    return round(dsr, 4)


# --------------------------------------------------------------------------- #
# Gate 2 — bootstrap overfit / fragility probability                           #
# --------------------------------------------------------------------------- #
def bootstrap_overfit_probability(r_series: List[float], n_boot: int = 2000,
                                  seed: int = 13) -> float:
    """Resample the trade sequence with replacement; the overfit/fragility proxy
    is the fraction of resamples whose expectancy is <= 0. A robust edge stays
    positive under resampling; an overfit one falls apart. Gate passes if <= 0.05.

    (Full CSCV-PBO needs a multi-config return matrix; that runs when the
    Discoverer proposes parameter variants. This single-config proxy is the
    honest lower bar.)"""
    if len(r_series) < 10:
        return 1.0
    rng = random.Random(seed)
    n = len(r_series)
    bad = 0
    for _ in range(n_boot):
        sample = [r_series[rng.randrange(n)] for _ in range(n)]
        if _mean(sample) <= 0:
            bad += 1
    return round(bad / n_boot, 4)


# --------------------------------------------------------------------------- #
# Gates 1 & 4 — walk-forward and out-of-sample (rerun the engine)             #
# --------------------------------------------------------------------------- #
@dataclass
class GateOutcome:
    name: str
    passed: bool
    value: float
    detail: str = ""


def walk_forward(engine: BacktestEngine, strategy, bars, n_windows: int = 5,
                 min_pass_fraction: float = 0.70, **run_kw) -> GateOutcome:
    if len(bars) < n_windows * (engine.warmup + 10):
        return GateOutcome("walkforward", False, 0.0, "insufficient data")
    size = len(bars) // n_windows
    positive = 0
    counted = 0
    for w in range(n_windows):
        seg = bars[w * size:(w + 1) * size]
        if len(seg) < engine.warmup + 5:
            continue
        res = engine.run(strategy, seg, **run_kw)
        if res.stats.n_trades == 0:
            continue
        counted += 1
        if res.stats.expectancy_r > 0:
            positive += 1
    frac = (positive / counted) if counted else 0.0
    return GateOutcome("walkforward", frac >= min_pass_fraction, round(frac, 3),
                       f"{positive}/{counted} windows positive")


def out_of_sample_ratio(engine: BacktestEngine, strategy, bars,
                        min_ratio: float = 0.50, **run_kw) -> GateOutcome:
    mid = len(bars) // 2
    is_res = engine.run(strategy, bars[:mid], **run_kw)
    oos_res = engine.run(strategy, bars[mid:], **run_kw)
    if is_res.stats.n_trades == 0 or oos_res.stats.n_trades == 0:
        return GateOutcome("oos", False, 0.0, "no trades in one half")
    ise = is_res.stats.expectancy_r
    oose = oos_res.stats.expectancy_r
    if ise <= 0:
        return GateOutcome("oos", False, 0.0, "in-sample expectancy non-positive")
    ratio = oose / ise
    return GateOutcome("oos", ratio >= min_ratio, round(ratio, 3),
                       f"IS={ise:.3f} OOS={oose:.3f}")


# --------------------------------------------------------------------------- #
# Aggregate                                                                    #
# --------------------------------------------------------------------------- #
@dataclass
class ValidationReport:
    walkforward: GateOutcome
    bootstrap: GateOutcome
    dsr: GateOutcome
    oos: GateOutcome
    paper_pending: bool = True

    def backtest_gates_passed(self) -> bool:
        return all(g.passed for g in (self.walkforward, self.bootstrap,
                                      self.dsr, self.oos))


def run_backtest_gates(engine: BacktestEngine, strategy, bars,
                       n_trials: int = 10, **run_kw) -> ValidationReport:
    full = engine.run(strategy, bars, **run_kw)
    r = full.r_series

    wf = walk_forward(engine, strategy, bars, **run_kw)
    pbo = bootstrap_overfit_probability(r)
    boot = GateOutcome("bootstrap_pbo", pbo <= 0.05, pbo, f"overfit prob {pbo}")
    dsr_v = deflated_sharpe_ratio(r, n_trials=n_trials)
    dsr = GateOutcome("deflated_sharpe", dsr_v > 0.95, dsr_v, f"DSR {dsr_v}")
    oos = out_of_sample_ratio(engine, strategy, bars, **run_kw)
    return ValidationReport(wf, boot, dsr, oos)
