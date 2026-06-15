import unittest

from src import config
from src.sizing.sizers import (
    StrategyStats, kelly_risk_pct, conviction_scaled, vol_adjusted,
    final_risk_dollars,
)


class TestSizing(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()

    def test_unproven_uses_half_pct(self):
        s = StrategyStats(n_trades=10, win_rate=0.6, avg_win_dollars=2, avg_loss_dollars=1)
        self.assertEqual(kelly_risk_pct(s, self.cfg), 0.005)

    def test_kelly_capped_at_1_5pct(self):
        # very favorable stats -> raw half-Kelly large, must cap at 1.5%
        s = StrategyStats(n_trades=100, win_rate=0.7, avg_win_dollars=3, avg_loss_dollars=1)
        self.assertLessEqual(kelly_risk_pct(s, self.cfg), 0.015 + 1e-12)

    def test_kelly_value_reasonable(self):
        # p=.55 b=1.5 -> f*=(1.5*.55-.45)/1.5 = (0.825-0.45)/1.5=0.25; half=0.125
        # capped to 0.015
        s = StrategyStats(n_trades=50, win_rate=0.55, avg_win_dollars=1.5, avg_loss_dollars=1)
        self.assertEqual(kelly_risk_pct(s, self.cfg), 0.015)

    def test_negative_edge_kelly_zero(self):
        s = StrategyStats(n_trades=50, win_rate=0.3, avg_win_dollars=1, avg_loss_dollars=1)
        self.assertEqual(kelly_risk_pct(s, self.cfg), 0.0)

    def test_conviction_scaling_at_floor_is_60pct(self):
        out = conviction_scaled(100.0, 72, self.cfg)  # at floor
        self.assertAlmostEqual(out, 60.0, places=6)

    def test_conviction_scaling_at_90_is_100pct(self):
        out = conviction_scaled(100.0, 90, self.cfg)
        self.assertAlmostEqual(out, 100.0, places=6)

    def test_conviction_scaling_midpoint(self):
        # conviction 81 -> halfway between 72 and 90 -> 0.6 + 0.4*0.5 = 0.8
        out = conviction_scaled(100.0, 81, self.cfg)
        self.assertAlmostEqual(out, 80.0, places=6)

    def test_vol_adjust_scales_down_in_high_vol(self):
        # realized 0.24 vs target 0.12 -> scalar 0.5
        self.assertAlmostEqual(vol_adjusted(100.0, 0.24, self.cfg), 50.0, places=6)

    def test_vol_adjust_capped_up(self):
        self.assertAlmostEqual(vol_adjusted(100.0, 0.01, self.cfg), 150.0, places=6)

    def test_final_is_minimum_constraint(self):
        s = StrategyStats(n_trades=100, win_rate=0.6, avg_win_dollars=2, avg_loss_dollars=1)
        out = final_risk_dollars(
            stats=s, equity=1500, realized_vol_20d=0.5, conviction=72,
            available_daily_risk_budget=5.0, cfg=self.cfg)
        # daily budget $5 is the binding (smallest) constraint here
        self.assertEqual(out, 5.0)


if __name__ == "__main__":
    unittest.main()
