import unittest

from src.killswitch import KillswitchState, evaluate, most_severe, HaltScope


class TestKillswitch(unittest.TestCase):
    def fired_names(self, **kw):
        s = KillswitchState(**kw)
        return {h.name for h in evaluate(s)}

    def test_clean_state_no_halt(self):
        self.assertEqual(self.fired_names(), set())

    def test_daily_loss_limit(self):
        self.assertIn("daily_loss_limit",
                      self.fired_names(day_pnl=-80, session_start_equity=1500))

    def test_drawdown_from_ath(self):
        self.assertIn("drawdown_from_ath",
                      self.fired_names(equity=1100, ath_equity=1500))

    def test_catastrophic(self):
        names = self.fired_names(equity=1000, catastrophic_floor=1050, ath_equity=1500)
        self.assertIn("catastrophic", names)

    def test_halt_flag(self):
        self.assertIn("halt_flag", self.fired_names(halt_flag=True))

    def test_five_losses_cooldown_not_day_halt(self):
        names = self.fired_names(consecutive_losses=5)
        self.assertIn("five_consecutive_losses", names)
        self.assertNotIn("eight_consecutive_losses", names)

    def test_eight_losses_halts_day(self):
        names = self.fired_names(consecutive_losses=8)
        self.assertIn("eight_consecutive_losses", names)

    def test_budget_pause_keeps_tier0(self):
        s = KillswitchState(llm_daily_spent=5.0, llm_daily_budget=5.0)
        halts = evaluate(s)
        budget = [h for h in halts if h.name == "daily_llm_budget"][0]
        self.assertEqual(budget.scope, HaltScope.BUDGET_PAUSE)

    def test_conviction_bypass_halts(self):
        self.assertIn("conviction_bypass",
                      self.fired_names(conviction_bypass_detected=True))

    def test_thesis_less_halts(self):
        self.assertIn("thesis_less_trade",
                      self.fired_names(thesis_less_order_detected=True))

    def test_unhedged_position(self):
        self.assertIn("unhedged_position",
                      self.fired_names(unhedged_position_detected=True))

    def test_latency_breach(self):
        self.assertIn("latency_budget_breach_pattern",
                      self.fired_names(decision_timeout_rate=0.4))

    def test_most_severe_orders_by_scope(self):
        s = KillswitchState(halt_flag=True, equity=1000, catastrophic_floor=1050,
                            ath_equity=1500)
        # catastrophic (indefinite) must outrank halt_session
        self.assertEqual(most_severe(s).name, "catastrophic")


if __name__ == "__main__":
    unittest.main()
