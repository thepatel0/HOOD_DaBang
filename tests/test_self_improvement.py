import unittest

from src.self_improvement.guard import (can_modify_path, can_modify_config_key,
                                        assert_allowed_path)
from src.self_improvement.golden import (GoldenSet, GoldenSample, judge, accuracy,
                                        brier_score, seed_default_golden)
from src.self_improvement.shadow import (ShadowComparison, MetaPrompter,
                                        PromptCandidate)


class TestRecursiveConstraint(unittest.TestCase):
    def test_blocks_risk(self):
        self.assertFalse(can_modify_path("src/risk.py").allowed)

    def test_blocks_killswitch(self):
        self.assertFalse(can_modify_path("src/killswitch.py").allowed)

    def test_blocks_reconciliation(self):
        self.assertFalse(can_modify_path("src/reconciliation.py").allowed)

    def test_blocks_gate_floors(self):
        self.assertFalse(can_modify_path("src/conviction/gate.py").allowed)

    def test_blocks_tests(self):
        self.assertFalse(can_modify_path("tests/test_risk.py").allowed)

    def test_allows_agent_prompt(self):
        self.assertTrue(can_modify_path("src/agents/intel.py").allowed)

    def test_config_key_protection(self):
        self.assertFalse(can_modify_config_key("risk.per_trade_risk_pct").allowed)
        self.assertFalse(can_modify_config_key("conviction.execution_floor").allowed)
        self.assertTrue(can_modify_config_key("screener.watchlist_max_names").allowed)

    def test_assert_raises(self):
        with self.assertRaises(PermissionError):
            assert_allowed_path("src/killswitch.py")


class TestGolden(unittest.TestCase):
    def test_seed_set_categories(self):
        g = seed_default_golden()
        self.assertGreaterEqual(len(g), 5)
        self.assertTrue(g.by_category("should_refuse"))

    def test_judge_accuracy(self):
        g = GoldenSet()
        g.add(GoldenSample("a", "perfect_orb", {"x": 1}, "trade"))
        g.add(GoldenSample("b", "obvious_skip", {"x": 0}, "pass"))
        # perfect agent
        results = judge(g, lambda s: "trade" if s["x"] else "pass")
        self.assertEqual(accuracy(results), 1.0)
        # broken agent
        results = judge(g, lambda s: "trade")
        self.assertEqual(accuracy(results), 0.5)

    def test_brier_score(self):
        # perfect calibration -> 0; worst -> 1
        self.assertAlmostEqual(brier_score([1.0, 0.0], [1, 0]), 0.0)
        self.assertAlmostEqual(brier_score([0.0, 1.0], [1, 0]), 1.0)


class TestShadow(unittest.TestCase):
    def test_extend_when_insufficient(self):
        c = ShadowComparison()
        c.record(1.0, 1.1)
        self.assertEqual(c.decide(min_n=5), "extend")

    def test_promote_when_shadow_better(self):
        c = ShadowComparison()
        for _ in range(6):
            c.record(1.0, 1.3)
        self.assertEqual(c.decide(threshold=0.1), "promote")

    def test_discard_when_shadow_worse(self):
        c = ShadowComparison()
        for _ in range(6):
            c.record(1.0, 0.5)
        self.assertEqual(c.decide(), "discard")


class TestMetaPrompter(unittest.TestCase):
    def setUp(self):
        self.mp = MetaPrompter(min_sample=30)

    def test_rejects_protected_path(self):
        cand = PromptCandidate("c1", "better prompt", target_path="src/risk.py")
        d = self.mp.evaluate("base", cand, [0.5] * 40, [0.9] * 40)
        self.assertFalse(d.adopt)
        self.assertIn("protected", d.reason)

    def test_adopts_significant_improvement(self):
        cand = PromptCandidate("c2", "p", target_path="src/agents/intel.py")
        base = [0.5 + (i % 3) * 0.01 for i in range(40)]
        better = [0.8 + (i % 3) * 0.01 for i in range(40)]
        d = self.mp.evaluate("baseline prompt", cand, base, better)
        self.assertTrue(d.adopt)

    def test_rejects_insignificant(self):
        cand = PromptCandidate("c3", "p", target_path="src/agents/intel.py")
        base = [0.5 + (i % 5) * 0.01 for i in range(40)]
        d = self.mp.evaluate("baseline", cand, base, list(base))
        self.assertFalse(d.adopt)

    def test_longer_prompt_needs_bigger_gain(self):
        # significant but small gain with a 2x-longer prompt -> rejected on cost
        cand = PromptCandidate("c4", "x" * 200, target_path="src/agents/intel.py")
        base = [0.50] * 20 + [0.52] * 20
        better = [0.55] * 20 + [0.57] * 20   # ~10% better, significant, but +<50%
        d = self.mp.evaluate("x" * 100, cand, base, better)
        self.assertFalse(d.adopt)
        self.assertIn("cost", d.reason)


if __name__ == "__main__":
    unittest.main()
