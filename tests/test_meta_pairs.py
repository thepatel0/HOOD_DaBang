import unittest

from src.agents.meta_learner import MetaLearner
from src.self_improvement.golden import GoldenSet, GoldenSample
from src.self_improvement.shadow import PromptCandidate
from src.strategies.stat_arb.pairs_evaluator import PairsEvaluator


def golden():
    g = GoldenSet()
    g.add(GoldenSample("a", "perfect_orb", {"x": 1}, "trade"))
    g.add(GoldenSample("b", "obvious_skip", {"x": 0}, "pass"))
    return g


class TestMetaLearner(unittest.TestCase):
    def setUp(self):
        self.ml = MetaLearner()
        self.g = golden()

    def test_detects_regression(self):
        ev = self.ml.evaluate_agent("news", self.g, lambda s: "trade", baseline=1.0)
        self.assertTrue(ev.regressed)             # always-"trade" agent is 50% acc

    def test_no_regression_for_good_agent(self):
        ev = self.ml.evaluate_agent("news", self.g,
                                    lambda s: "trade" if s["x"] else "pass", baseline=1.0)
        self.assertFalse(ev.regressed)
        self.assertEqual(ev.accuracy, 1.0)

    def test_run_promotes_significant_revision(self):
        agents = {"news": lambda s: "trade"}     # regressed
        revisions = {"news": ("base prompt", PromptCandidate("v2", "p",
                     target_path="src/agents/intel.py"),
                     [0.5] * 40, [0.85] * 40)}
        report = self.ml.run(agents, self.g, {"news": 1.0}, revisions)
        self.assertIn("news", report.promotions_to_shadow)

    def test_run_rejects_protected_path_revision(self):
        agents = {"news": lambda s: "trade"}
        revisions = {"news": ("base", PromptCandidate("v2", "p",
                     target_path="src/risk.py"), [0.5] * 40, [0.9] * 40)}
        report = self.ml.run(agents, self.g, {"news": 1.0}, revisions)
        self.assertEqual(report.promotions_to_shadow, [])
        self.assertTrue(report.rejected)


class TestPairsEvaluator(unittest.TestCase):
    def setUp(self):
        self.e = PairsEvaluator()

    def test_enter_on_divergence(self):
        b = [100.0] * 25
        a = [100.0] * 24 + [112.0]                # a spikes -> short a, long b
        d = self.e.evaluate("MA", "V", a, b)
        self.assertEqual(d.action, "enter")
        self.assertEqual(d.short_leg, "MA")
        self.assertEqual(d.long_leg, "V")

    def test_hold_then_exit_on_reversion(self):
        b = [100.0] * 25
        a = [100.0] * 24 + [112.0]
        self.e.evaluate("MA", "V", a, b)          # enter
        # spread reverts -> exit
        a2 = [100.0] * 25
        d = self.e.evaluate("MA", "V", a2, b)
        self.assertEqual(d.action, "exit")
        self.assertEqual(d.reason, "spread_reverted")

    def test_no_entry_when_z_small(self):
        prices = [100.0 + (i % 2) * 0.5 for i in range(25)]
        d = self.e.evaluate("MA", "V", prices, prices)
        self.assertEqual(d.action, "hold")

    def test_insufficient_data(self):
        d = self.e.evaluate("MA", "V", [1, 2, 3], [1, 2, 3])
        self.assertEqual(d.reason, "insufficient_data")


if __name__ == "__main__":
    unittest.main()
