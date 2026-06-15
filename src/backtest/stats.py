"""
HOOD DaBang — backtest statistics (Brief §9).

Reports the FULL stat set the brief demands — never just cumulative return:
expectancy, hit rate, avg R, max drawdown, longest losing streak, Sharpe,
Sortino, Calmar, profit factor. Operates on a list of per-trade R-multiples and
an equity curve. Pure math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class Stats:
    n_trades: int = 0
    win_rate: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    longest_losing_streak: int = 0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    total_r: float = 0.0


def _std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def compute_stats(r_multiples: List[float], equity_curve: List[float],
                  periods_per_year: int = 252) -> Stats:
    s = Stats()
    n = len(r_multiples)
    s.n_trades = n
    if n == 0:
        return s

    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r <= 0]
    s.win_rate = len(wins) / n
    s.avg_win_r = (sum(wins) / len(wins)) if wins else 0.0
    s.avg_loss_r = (sum(losses) / len(losses)) if losses else 0.0
    s.total_r = sum(r_multiples)
    s.expectancy_r = s.total_r / n

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    s.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    # longest losing streak
    streak = best = 0
    for r in r_multiples:
        if r <= 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    s.longest_losing_streak = best

    # drawdown on the equity curve
    peak = equity_curve[0] if equity_curve else 0.0
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)
    s.max_drawdown = max_dd

    # Sharpe / Sortino on per-trade returns (in R units, treated as the series)
    sd = _std(r_multiples)
    mean_r = s.expectancy_r
    s.sharpe = (mean_r / sd * math.sqrt(min(periods_per_year, n))) if sd > 0 else 0.0
    downside = [r for r in r_multiples if r < 0]
    dsd = _std(downside) if len(downside) >= 2 else (abs(downside[0]) if downside else 0.0)
    s.sortino = (mean_r / dsd * math.sqrt(min(periods_per_year, n))) if dsd > 0 else 0.0

    # Calmar = total return / max drawdown
    if equity_curve and equity_curve[0] > 0 and s.max_drawdown > 0:
        total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
        s.calmar = total_return / s.max_drawdown

    for k in ("win_rate", "avg_win_r", "avg_loss_r", "expectancy_r", "profit_factor",
              "max_drawdown", "sharpe", "sortino", "calmar", "total_r"):
        v = getattr(s, k)
        if v not in (float("inf"), float("-inf")):
            setattr(s, k, round(v, 4))
    return s
