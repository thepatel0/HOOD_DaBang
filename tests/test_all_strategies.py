import unittest

from src.strategies.all import (build_full_registry, all_strategies,
                                derive_allocations, REGIMES, ALL_STRATEGY_CLASSES)
from src.strategies.base import Strategy


class TestAllStrategies(unittest.TestCase):
    def test_nineteen_strategies(self):
        self.assertEqual(len(ALL_STRATEGY_CLASSES), 19)

    def test_all_instantiate_and_have_required_attrs(self):
        for s in all_strategies():
            self.assertIsInstance(s, Strategy)
            self.assertTrue(s.name)
            self.assertTrue(s.version)
            self.assertIn(s.activation_status,
                          ("development", "backtested", "paper", "live", "paused"))
            self.assertIsInstance(s.regime_preferences, dict)

    def test_unique_names(self):
        names = [s.name for s in all_strategies()]
        self.assertEqual(len(names), len(set(names)))

    def test_registry_registers_all(self):
        reg = build_full_registry()
        self.assertEqual(len(reg.all()), 19)

    def test_intraday_paper_swing_development(self):
        reg = build_full_registry(activation="paper")
        self.assertEqual(reg.get("orb").strategy.activation_status, "paper")
        # swing strategies stay in development until Day 30
        self.assertEqual(reg.get("pead").strategy.activation_status, "development")

    def test_allocations_cover_all_regimes(self):
        alloc = derive_allocations(all_strategies())
        for r in REGIMES:
            self.assertIn(r, alloc)

    def test_crisis_favors_pairs(self):
        alloc = derive_allocations(all_strategies())
        # pairs should have the largest crisis allocation
        crisis = alloc["crisis"]
        self.assertEqual(max(crisis, key=crisis.get), "pairs")

    def test_allocations_normalized(self):
        alloc = derive_allocations(all_strategies())
        for r, weights in alloc.items():
            if weights:
                self.assertAlmostEqual(sum(weights.values()), 1.0, places=3)

    def test_every_strategy_scan_manage_callable(self):
        from src.strategies.base import MarketState
        ms = MarketState(ticker="X", now_et="2026-06-15T11:00:00-04:00", quote=100.0)
        for s in all_strategies():
            # scan must not raise on a bare MarketState (returns [] when data absent)
            out = s.scan(ms)
            self.assertIsInstance(out, list)


if __name__ == "__main__":
    unittest.main()
