"""
HOOD DaBang — strategy validation tool.

Runs a strategy through the backtest + the five validation gates on REAL data.
Only a strategy that clears ALL gates earns promotion to `live`.

  PYTHONPATH=. .venv/bin/python scripts/validate_strategy.py --ticker SPY --strategy orb

Most strategies will FAIL on raw data — that is the system working (backtest
Sharpe predicts live at R^2<0.025). Real edge needs proper catalyst/regime
filtering and walk-forward tuning; this tool tells you the honest truth.
"""
from __future__ import annotations

import argparse
import socket

from src import config
from src.data_feeds.bars import CachedBarFeed
from src.backtest.engine import BacktestEngine
from src.backtest.validation import run_backtest_gates
from src.strategies.all import all_strategies


def main(argv=None) -> int:
    socket.setdefaulttimeout(30)
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="SPY")
    p.add_argument("--strategy", default="orb")
    p.add_argument("--interval", default="5m")
    p.add_argument("--days", type=int, default=5)
    p.add_argument("--regime", default="bull_trend_low_vol")
    args = p.parse_args(argv)

    strat = next((s for s in all_strategies() if s.name == args.strategy), None)
    if strat is None:
        print(f"unknown strategy {args.strategy!r}; choices: "
              f"{[s.name for s in all_strategies()]}")
        return 2

    cfg = config.load()
    feed = CachedBarFeed(ttl_s=600)
    res = feed.get_bars(args.ticker, interval=args.interval, lookback_days=args.days)
    if len(res.bars) < 60:
        print(f"insufficient data for {args.ticker} ({len(res.bars)} bars, "
              f"degraded={res.degraded})")
        return 1

    eng = BacktestEngine(cfg, warmup=12, det_floor=60)
    run_kw = dict(ticker=args.ticker, regime=args.regime, prior_close=res.bars[0].o,
                  has_catalyst=True, catalyst_age_min=5, catalyst_sources=2)
    bt = eng.run(strat, res.bars, **run_kw)
    s = bt.stats

    print(f"=== {args.strategy} on {args.ticker} {args.interval} "
          f"({len(res.bars)} bars) ===")
    print(f"trades={s.n_trades} expectancy={s.expectancy_r:+.3f}R win={s.win_rate:.0%} "
          f"avgWin={s.avg_win_r:+.2f}R avgLoss={s.avg_loss_r:+.2f}R")
    print(f"maxDD={s.max_drawdown:.1%} Sharpe={s.sharpe:.2f} Sortino={s.sortino:.2f} "
          f"Calmar={s.calmar:.2f} profitFactor={s.profit_factor:.2f} "
          f"longestLoseStreak={s.longest_losing_streak}")

    rep = run_backtest_gates(eng, strat, res.bars, **run_kw)
    print("\nValidation gates:")
    for g in (rep.walkforward, rep.bootstrap, rep.dsr, rep.oos):
        mark = "PASS" if g.passed else "FAIL"
        print(f"  [{mark}] {g.name}: {g.detail}")
    print(f"  [{'PASS' if False else 'PENDING'}] paper: needs >=30 live forward trades")
    ok = rep.backtest_gates_passed()
    print(f"\n{'PROMOTE-ELIGIBLE (after paper gate)' if ok else 'NOT eligible for live'} "
          f"— backtest gates {'all pass' if ok else 'do not all pass'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
