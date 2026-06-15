import unittest

from src import config
from src.strategies.intraday.orb import OpeningRangeBreakout
from src.backtest.engine import BacktestEngine
from src.backtest.validation import (
    deflated_sharpe_ratio, bootstrap_overfit_probability, skewness, kurtosis,
    per_trade_sharpe, run_backtest_gates,
)
from tests.test_backtest import orb_win_bars


class TestMoments(unittest.TestCase):
    def test_symmetric_skew_zero(self):
        self.assertAlmostEqual(skewness([-2, -1, 0, 1, 2]), 0.0, places=6)

    def test_kurtosis_reasonable(self):
        import random
        rng = random.Random(0)
        data = [rng.gauss(0, 1) for _ in range(2000)]
        self.assertTrue(2.0 < kurtosis(data) < 4.0)  # ~3 for normal

    def test_per_trade_sharpe_positive(self):
        self.assertGreater(per_trade_sharpe([0.5] * 40 + [-0.3] * 20), 0)


class TestDeflatedSharpe(unittest.TestCase):
    def test_strong_series_passes(self):
        r = [0.5] * 40 + [-0.3] * 20  # consistent positive edge
        dsr = deflated_sharpe_ratio(r, n_trials=10)
        self.assertGreater(dsr, 0.95)

    def test_zero_mean_series_fails(self):
        r = [0.3, -0.3] * 30  # no edge
        dsr = deflated_sharpe_ratio(r, n_trials=10)
        self.assertLess(dsr, 0.6)

    def test_more_trials_lowers_dsr(self):
        r = [0.5] * 40 + [-0.3] * 20
        few = deflated_sharpe_ratio(r, n_trials=2)
        many = deflated_sharpe_ratio(r, n_trials=500)
        self.assertGreater(few, many)   # deflation for more trials

    def test_too_few_trades_zero(self):
        self.assertEqual(deflated_sharpe_ratio([0.5, 0.5], n_trials=10), 0.0)


class TestBootstrapOverfit(unittest.TestCase):
    def test_robust_edge_low_overfit(self):
        r = [0.5] * 40 + [-0.3] * 20
        self.assertLess(bootstrap_overfit_probability(r), 0.05)

    def test_no_edge_high_overfit(self):
        r = [0.3, -0.3] * 30
        self.assertGreater(bootstrap_overfit_probability(r), 0.3)

    def test_short_series_max_overfit(self):
        self.assertEqual(bootstrap_overfit_probability([1, -1, 1]), 1.0)


class TestGateIntegration(unittest.TestCase):
    def test_insufficient_data_fails_gates_honestly(self):
        cfg = config.load()
        engine = BacktestEngine(cfg, warmup=10, det_floor=60)
        report = run_backtest_gates(engine, OpeningRangeBreakout(), orb_win_bars(),
                                    regime="bull_trend_low_vol", prior_close=100.0)
        # one trade can't clear the gates -> the system must NOT pass it
        self.assertFalse(report.backtest_gates_passed())
        self.assertTrue(report.paper_pending)
        # but the report is well-formed
        self.assertEqual(report.dsr.name, "deflated_sharpe")
        self.assertEqual(report.bootstrap.name, "bootstrap_pbo")


if __name__ == "__main__":
    unittest.main()
