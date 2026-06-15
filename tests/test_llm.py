import unittest
from datetime import datetime, timezone

from src import config, db
from src.llm_budget import LLMBudget
from src.llm_client import LLMClient, MockLLMTransport, TierMismatch


FIXED_NOW = lambda: datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc)


def fresh_budget():
    conn = db.init_ledger(":memory:")
    return LLMBudget(conn, config.load(), now=FIXED_NOW)


class TestLLMBudget(unittest.TestCase):
    def test_cost_model(self):
        b = fresh_budget()
        # sonnet: 10k input @ $3/Mtok + 1k output @ $15/Mtok = 0.03 + 0.015 = 0.045
        self.assertAlmostEqual(b.cost("sonnet-4.6", 10000, 1000), 0.045, places=6)

    def test_cache_discount(self):
        b = fresh_budget()
        full = b.cost("sonnet-4.6", 10000, 1000, cached_tokens=0)
        cached = b.cost("sonnet-4.6", 10000, 1000, cached_tokens=9000)
        self.assertLess(cached, full)

    def test_record_and_aggregate(self):
        b = fresh_budget()
        c1 = b.record("macro", "sonnet-4.6", 10000, 1000)
        c2 = b.record("news", "haiku-4.5", 5000, 500)
        self.assertAlmostEqual(b.spent_today(), c1 + c2, places=9)
        self.assertAlmostEqual(b.spent_month(), c1 + c2, places=9)

    def test_state_reflects_spend(self):
        b = fresh_budget()
        b.record("trader", "opus-4.8", 2_000_000, 200_000)  # huge -> over $5
        st = b.state()
        self.assertTrue(st.daily_exhausted)

    def test_cache_hit_rate(self):
        b = fresh_budget()
        b.record("macro", "sonnet-4.6", 10000, 1000, cached_tokens=8000)
        self.assertAlmostEqual(b.cache_hit_rate(), 0.8, places=6)


class TestLLMClient(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.budget = fresh_budget()
        self.transport = MockLLMTransport(text='{"ok":true}',
                                          input_tokens=10000, output_tokens=800)
        self.client = LLMClient(self.cfg, self.budget, self.transport)

    def test_tier2_uses_sonnet_not_opus(self):
        r = self.client.call("macro_synthesis", "macro", "sys", [{"role": "user",
                             "content": "hi"}])
        self.assertTrue(r.spent)
        self.assertEqual(r.model, "sonnet-4.6")
        self.assertEqual(self.transport.calls[0]["model"], "sonnet-4.6")

    def test_gated_task_not_survivor_no_spend(self):
        r = self.client.call("trader_synthesis", "trader", "sys",
                             [{"role": "user", "content": "x"}],
                             is_gate_survivor=False)
        self.assertFalse(r.spent)
        self.assertEqual(len(self.transport.calls), 0)

    def test_gated_task_survivor_spends(self):
        r = self.client.call("trader_synthesis", "trader", "sys",
                             [{"role": "user", "content": "x"}],
                             is_gate_survivor=True)
        self.assertTrue(r.spent)
        self.assertEqual(r.model, "opus-4.8")

    def test_budget_exhausted_degrades(self):
        self.budget.record("trader", "opus-4.8", 2_000_000, 200_000)  # blow the budget
        r = self.client.call("macro_synthesis", "macro", "sys",
                             [{"role": "user", "content": "x"}])
        self.assertFalse(r.spent)
        self.assertIn("budget", r.reason)

    def test_tier_mismatch_raises(self):
        # route a sonnet-tier task but pass a haiku-tier agent -> mismatch
        with self.assertRaises(TierMismatch):
            self.client.call("bull_debate", "news", "sys",
                             [{"role": "user", "content": "x"}],
                             is_gate_survivor=True)

    def test_ledger_sum_matches_known_cost(self):
        # §15 test #15: ledger cost reconciles to a manual computation within 1%
        for _ in range(5):
            self.client.call("macro_synthesis", "macro", "sys",
                             [{"role": "user", "content": "x"}])
        expected = 5 * self.budget.cost("sonnet-4.6", 10000, 800)
        self.assertAlmostEqual(self.budget.spent_today(), expected,
                               delta=expected * 0.01)


if __name__ == "__main__":
    unittest.main()
