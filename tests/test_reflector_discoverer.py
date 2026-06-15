import unittest

from src.agents.reflector import Reflector
from src.agents.discoverer import Discoverer


class TestReflector(unittest.TestCase):
    def setUp(self):
        self.r = Reflector()

    def test_win_is_na_loss_category(self):
        ref = self.r.reflect_trade(trade_id=1, ticker="AAPL", side="long", pnl_r=1.5,
                                   exit_reason="target", base_rate=0.55)
        self.assertEqual(ref.good_or_bad_loss, "n/a")
        self.assertTrue(ref.mechanism_was_correct)

    def test_clean_stop_is_good_loss(self):
        ref = self.r.reflect_trade(trade_id=2, ticker="X", side="long", pnl_r=-1.0,
                                   exit_reason="stop", base_rate=0.5)
        self.assertEqual(ref.good_or_bad_loss, "good")
        self.assertTrue(ref.invalidation_fired_correctly)

    def test_manual_exit_is_bad_loss(self):
        ref = self.r.reflect_trade(trade_id=3, ticker="X", side="long", pnl_r=-1.0,
                                   exit_reason="manual_chased", base_rate=0.5)
        self.assertEqual(ref.good_or_bad_loss, "bad")

    def test_ignored_invalidation_is_bad(self):
        ref = self.r.reflect_trade(trade_id=4, ticker="X", side="long", pnl_r=-2.0,
                                   exit_reason="stop", base_rate=0.5,
                                   invalidation_should_have_fired=True)
        self.assertEqual(ref.good_or_bad_loss, "bad")

    def test_base_rate_accuracy(self):
        ref = self.r.reflect_trade(trade_id=5, ticker="X", side="long", pnl_r=1.0,
                                   exit_reason="target", base_rate=0.6)
        self.assertTrue(ref.base_rate_was_accurate)   # win matched >50% base rate

    def test_session_overtrading_flag(self):
        trades = [{"pnl_r": 0.1, "good_or_bad_loss": "n/a"} for _ in range(12)]
        sr = self.r.reflect_session(trades, ceiling=10)
        self.assertTrue(sr.overtrading_flag)
        self.assertIn("OVERTRADING", sr.notes)

    def test_session_no_overtrading(self):
        trades = [{"pnl_r": 1.0, "good_or_bad_loss": "n/a"},
                  {"pnl_r": -1.0, "good_or_bad_loss": "good"}]
        sr = self.r.reflect_session(trades, ceiling=10)
        self.assertFalse(sr.overtrading_flag)
        self.assertEqual(sr.wins, 1)


class TestDiscoverer(unittest.TestCase):
    def setUp(self):
        self.d = Discoverer(min_sample=5)

    def _trades(self, strategy, regime, r, n):
        return [{"strategy": strategy, "market_regime": regime, "pnl_r": r}
                for _ in range(n)]

    def test_mines_promising_pattern(self):
        trades = self._trades("orb", "bull_trend_low_vol", 0.5, 10)
        patterns = self.d.mine(trades)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].direction, "promising")

    def test_mines_degrading_pattern(self):
        trades = self._trades("vwap_reversion", "bull_trend_high_vol", -0.4, 10)
        patterns = self.d.mine(trades)
        self.assertEqual(patterns[0].direction, "degrading")

    def test_ignores_small_samples(self):
        self.assertEqual(self.d.mine(self._trades("orb", "range_low_vol", 0.5, 3)), [])

    def test_neutral_patterns_dropped(self):
        self.assertEqual(self.d.mine(self._trades("orb", "range_low_vol", 0.0, 10)), [])

    def test_hypotheses_generated(self):
        patterns = self.d.mine(self._trades("orb", "bull_trend_low_vol", 0.5, 10))
        hyps = self.d.to_hypotheses(patterns)
        self.assertEqual(len(hyps), 1)
        self.assertEqual(hyps[0].direction, "greater")
        self.assertIn("discover:", hyps[0].id)


if __name__ == "__main__":
    unittest.main()
