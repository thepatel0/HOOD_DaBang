import unittest

from src import config
from src.strategies.base import Bar
from src.strategies.intraday.orb import OpeningRangeBreakout
from src.backtest.engine import BacktestEngine
from src.backtest.stats import compute_stats


def orb_win_bars():
    """40 1-min bars: opening range 100-101, a breakout at i=12 that runs to a
    fast target, then back inside range (no re-entry). Yields one winning trade."""
    bars = []
    def ts(i): return f"2026-06-15T{9 + (30 + i)//60:02d}:{(30 + i)%60:02d}:00-04:00"
    # i0-4: opening range high=101, low=100
    for i in range(5):
        bars.append(Bar(ts(i), 100.4, 101.0, 100.0, 100.5, 2000))
    # i5-11: inside range, quiet
    for i in range(5, 12):
        bars.append(Bar(ts(i), 100.5, 100.9, 100.2, 100.6, 1500))
    # i12: breakout bar, close above OR-high, big volume
    bars.append(Bar(ts(12), 100.7, 101.6, 100.6, 101.5, 12000))
    # i13: gap up & run -> target hit fast (high to 110)
    bars.append(Bar(ts(13), 101.5, 110.0, 101.4, 108.0, 15000))
    # i14-39: back inside range, no new setup
    for i in range(14, 40):
        bars.append(Bar(ts(i), 100.5, 100.8, 100.3, 100.5, 1200))
    return bars


class TestStats(unittest.TestCase):
    def test_known_series(self):
        r = [1.5, -1.0, 1.5, -1.0]
        eq = [1500, 1522.5, 1507.5, 1530, 1515]
        s = compute_stats(r, eq)
        self.assertEqual(s.n_trades, 4)
        self.assertAlmostEqual(s.win_rate, 0.5)
        self.assertAlmostEqual(s.expectancy_r, 0.25)
        self.assertAlmostEqual(s.avg_win_r, 1.5)
        self.assertAlmostEqual(s.avg_loss_r, -1.0)
        self.assertAlmostEqual(s.profit_factor, 1.5)
        self.assertEqual(s.longest_losing_streak, 1)

    def test_empty(self):
        s = compute_stats([], [1500])
        self.assertEqual(s.n_trades, 0)

    def test_all_losses_streak(self):
        s = compute_stats([-1, -1, -1], [1500, 1485, 1470, 1455])
        self.assertEqual(s.longest_losing_streak, 3)
        self.assertEqual(s.win_rate, 0.0)


class TestBacktestEngine(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.engine = BacktestEngine(self.cfg, warmup=10, det_floor=60)

    def test_produces_winning_trade(self):
        res = self.engine.run(OpeningRangeBreakout(), orb_win_bars(),
                              regime="bull_trend_low_vol", prior_close=100.0)
        self.assertGreaterEqual(len(res.trades), 1)
        first = res.trades[0]
        self.assertEqual(first.side, "long")
        self.assertGreater(first.r_multiple, 0)   # winner
        self.assertEqual(first.reason, "target")

    def test_slippage_reduces_pnl(self):
        no_slip = BacktestEngine(self.cfg, slippage_pct=0.0, warmup=10, det_floor=60)
        hi_slip = BacktestEngine(self.cfg, slippage_pct=0.01, warmup=10, det_floor=60)
        r0 = no_slip.run(OpeningRangeBreakout(), orb_win_bars(),
                         regime="bull_trend_low_vol", prior_close=100.0)
        r1 = hi_slip.run(OpeningRangeBreakout(), orb_win_bars(),
                         regime="bull_trend_low_vol", prior_close=100.0)
        self.assertGreater(r0.trades[0].r_multiple, r1.trades[0].r_multiple)

    def test_no_look_ahead(self):
        """Corrupting far-future bars must NOT change a trade that already
        completed earlier (the §15 future-data-trap test)."""
        bars = orb_win_bars()
        clean = self.engine.run(OpeningRangeBreakout(), bars,
                                regime="bull_trend_low_vol", prior_close=100.0)
        corrupted = [b for b in bars]
        for i in range(20, len(corrupted)):  # garbage AFTER the trade completed
            corrupted[i] = Bar(corrupted[i].ts, 500, 9999, 1, 0.01, 99)
        dirty = self.engine.run(OpeningRangeBreakout(), corrupted,
                                regime="bull_trend_low_vol", prior_close=100.0)
        self.assertEqual(clean.trades[0].entry, dirty.trades[0].entry)
        self.assertEqual(clean.trades[0].exit, dirty.trades[0].exit)
        self.assertEqual(clean.trades[0].r_multiple, dirty.trades[0].r_multiple)


if __name__ == "__main__":
    unittest.main()
