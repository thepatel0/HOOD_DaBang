import unittest

from src.analysts_local.microstructure import MicrostructureAnalyst
from src.analysts_local.insider import InsiderAnalyst, Form4Txn


class TestMicrostructure(unittest.TestCase):
    def setUp(self):
        self.a = MicrostructureAnalyst()

    def test_rvol_computed(self):
        r = self.a.analyze(today_cum_volume=3_000_000, expected_cum_volume=1_000_000)
        self.assertAlmostEqual(r.rvol, 3.0)
        self.assertGreater(r.score, 50)

    def test_volume_spike(self):
        r = self.a.analyze(last_bar_volume=9000, avg_bar_volume=2000)
        self.assertTrue(r.volume_spike)

    def test_put_call_ratio_and_uoa(self):
        r = self.a.analyze(put_volume=300, call_volume=1000,
                           last_bar_volume=9000, avg_bar_volume=2000)
        self.assertAlmostEqual(r.put_call_ratio, 0.3)
        self.assertTrue(r.uoa_flag)              # bullish UOA confirmed by vol spike

    def test_uoa_requires_volume_confirmation(self):
        r = self.a.analyze(put_volume=300, call_volume=1000)  # no vol spike
        self.assertFalse(r.uoa_flag)

    def test_short_volume_ratio(self):
        r = self.a.analyze(short_volume=700, total_volume=1000)
        self.assertAlmostEqual(r.short_volume_ratio, 0.7)


class TestInsider(unittest.TestCase):
    def setUp(self):
        self.a = InsiderAnalyst()

    def test_cluster_buy(self):
        txns = [Form4Txn(f"insider{i}", "Director", "buy", 100_000, days_ago=5)
                for i in range(3)]
        r = self.a.analyze(txns)
        self.assertTrue(r.cluster_buy)
        self.assertEqual(r.n_buyers_30d, 3)
        self.assertGreater(r.score, 50)

    def test_large_buy(self):
        r = self.a.analyze([Form4Txn("ceo", "CEO", "buy", 600_000, days_ago=2)])
        self.assertTrue(r.large_buy)

    def test_large_buy_by_pct(self):
        r = self.a.analyze([Form4Txn("x", "Director", "buy", 50_000,
                                     pct_of_holdings=0.02, days_ago=2)])
        self.assertTrue(r.large_buy)

    def test_large_exec_sell_penalized(self):
        r = self.a.analyze([Form4Txn("cfo", "CFO", "sell", 6_000_000, days_ago=3)])
        self.assertTrue(r.large_exec_sell)
        self.assertLess(r.score, 50)

    def test_old_transactions_ignored(self):
        r = self.a.analyze([Form4Txn(f"i{i}", "Director", "buy", 100_000, days_ago=40)
                            for i in range(3)])
        self.assertFalse(r.cluster_buy)
        self.assertEqual(r.n_buyers_30d, 0)


if __name__ == "__main__":
    unittest.main()
