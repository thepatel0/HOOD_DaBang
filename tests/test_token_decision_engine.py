import unittest

from src.token_decision_engine import (
    TokenDecisionEngine, BudgetState, Tier,
)


def fresh_budget(**kw):
    d = dict(daily_spent_usd=0.0, daily_budget_usd=5.0, monthly_spent_usd=0.0,
             monthly_budget_usd=60.0, budget_pause_flag=False)
    d.update(kw)
    return BudgetState(**d)


class TestTokenDecisionEngine(unittest.TestCase):
    def setUp(self):
        self.tde = TokenDecisionEngine()

    def test_tier0_is_free(self):
        d = self.tde.route("technical_analysis", budget=fresh_budget())
        self.assertEqual(d.tier, Tier.LOCAL)
        self.assertFalse(d.spend_tokens)
        self.assertEqual(d.est_cost_usd, 0.0)

    def test_regime_classification_stays_local(self):
        # ML inference must never go to a model
        d = self.tde.route("regime_classification", budget=fresh_budget())
        self.assertFalse(d.spend_tokens)

    def test_news_routes_to_haiku(self):
        d = self.tde.route("news_classification", budget=fresh_budget(),
                           est_in_tokens=5000, est_out_tokens=500)
        self.assertEqual(d.tier, Tier.HAIKU)
        self.assertEqual(d.model, "haiku-4.5")
        self.assertTrue(d.spend_tokens)

    def test_cache_hit_short_circuits_to_free(self):
        d = self.tde.route("news_classification", budget=fresh_budget(),
                           cache_hit=True)
        self.assertFalse(d.spend_tokens)
        self.assertEqual(d.reason, "cache_hit_zero_cost")

    def test_gated_task_blocked_for_non_survivor(self):
        d = self.tde.route("bull_debate", budget=fresh_budget(),
                           is_gate_survivor=False)
        self.assertFalse(d.spend_tokens)
        self.assertEqual(d.reason, "not_gate_survivor_no_spend")

    def test_gated_task_allowed_for_survivor(self):
        d = self.tde.route("trader_synthesis", budget=fresh_budget(),
                           is_gate_survivor=True,
                           est_in_tokens=8000, est_out_tokens=800)
        self.assertEqual(d.tier, Tier.OPUS)
        self.assertTrue(d.spend_tokens)

    def test_budget_exhausted_degrades(self):
        d = self.tde.route("macro_synthesis",
                           budget=fresh_budget(daily_spent_usd=5.0))
        self.assertFalse(d.spend_tokens)
        self.assertTrue(d.degraded)
        self.assertIn("budget", d.reason)

    def test_budget_pause_flag_degrades(self):
        d = self.tde.route("sentiment_scoring",
                           budget=fresh_budget(budget_pause_flag=True))
        self.assertFalse(d.spend_tokens)
        self.assertTrue(d.degraded)

    def test_would_breach_budget_degrades(self):
        # a giant opus call that would push past the daily budget
        d = self.tde.route("trader_synthesis", is_gate_survivor=True,
                           budget=fresh_budget(daily_spent_usd=4.99),
                           est_in_tokens=2_000_000, est_out_tokens=200_000)
        self.assertFalse(d.spend_tokens)
        self.assertIn("would_breach", d.reason)

    def test_cost_estimate_uses_cache_discount(self):
        full = self.tde.estimate_cost("sonnet-4.6", 10000, 1000, cached_tokens=0)
        cached = self.tde.estimate_cost("sonnet-4.6", 10000, 1000, cached_tokens=9000)
        self.assertLess(cached, full)  # cached input ~90% cheaper

    def test_unknown_task_forced_local(self):
        d = self.tde.route("teleport_to_mars", budget=fresh_budget())
        self.assertFalse(d.spend_tokens)
        self.assertTrue(d.degraded)


if __name__ == "__main__":
    unittest.main()
