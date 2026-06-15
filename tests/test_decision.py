import unittest

from src import config
from src.decision.hypothesis import (
    Hypothesis, FalsificationEngine, permutation_test,
)
from src.decision import monte_carlo as mc
from src.decision.adaptive_risk import (
    AdaptiveRiskGovernor, RiskContext,
)
from src.sizing.sizers import StrategyStats


# --------------------------------------------------------------------------- #
# FALSIFICATION ENGINE                                                         #
# --------------------------------------------------------------------------- #
class TestFalsification(unittest.TestCase):
    def setUp(self):
        self.eng = FalsificationEngine()

    def test_insufficient_sample_does_not_adopt(self):
        h = Hypothesis("h1", "change helps", "change does nothing", min_sample=30)
        res = self.eng.evaluate(h, [1.0] * 5, [0.0] * 5)
        self.assertFalse(res.adopt)
        self.assertIn("insufficient_sample", res.reason)

    def test_real_effect_is_adopted(self):
        # treatment clearly better than control -> null rejected, adopt
        h = Hypothesis("h2", "treatment > control", "no diff", direction="greater",
                       min_sample=30)
        treatment = [1.0 + (i % 3) * 0.1 for i in range(60)]   # ~mean 1.1
        control = [0.0 + (i % 3) * 0.1 for i in range(60)]     # ~mean 0.1
        res = self.eng.evaluate(h, treatment, control, n_perm=2000)
        self.assertTrue(res.reject_null)
        self.assertTrue(res.adopt)
        self.assertLess(res.p_value, 0.05)

    def test_no_real_effect_is_not_adopted(self):
        # identical distributions -> null should stand (burden of proof on change)
        h = Hypothesis("h3", "treatment > control", "no diff", min_sample=30)
        base = [float(i % 5) for i in range(60)]
        res = self.eng.evaluate(h, list(base), list(base), n_perm=2000)
        self.assertFalse(res.adopt)

    def test_significant_but_wrong_direction_rejected(self):
        # treatment is WORSE but hypothesis claimed 'greater' -> must NOT adopt
        h = Hypothesis("h4", "treatment > control", "no diff", direction="greater",
                       min_sample=30)
        treatment = [0.0] * 60
        control = [1.0] * 60
        res = self.eng.evaluate(h, treatment, control, n_perm=2000)
        self.assertFalse(res.adopt)

    def test_permutation_p_never_zero(self):
        p, _ = permutation_test([5.0] * 30, [0.0] * 30, n_perm=500)
        self.assertGreater(p, 0.0)  # +1 smoothing: never claim certainty


# --------------------------------------------------------------------------- #
# MONTE-CARLO RUIN SIMULATION                                                  #
# --------------------------------------------------------------------------- #
class TestMonteCarlo(unittest.TestCase):
    def test_kelly_full_positive_edge(self):
        # p=.55, win_R=1, loss_R=1 -> f* = (.55-.45)/1 = 0.10
        self.assertAlmostEqual(mc.kelly_full_fraction(0.55, 1.0, 1.0), 0.10, places=6)

    def test_kelly_zero_for_losing_game(self):
        self.assertEqual(mc.kelly_full_fraction(0.40, 1.0, 1.0), 0.0)

    def test_ruin_rises_with_risk_fraction(self):
        # same edge, bigger bet -> strictly more ruin (the core argument)
        low = mc.simulate(0.52, 1.5, 1.0, 0.01, n_paths=1500, n_trades=200)
        high = mc.simulate(0.52, 1.5, 1.0, 0.06, n_paths=1500, n_trades=200)
        self.assertGreater(high.prob_ruin, low.prob_ruin)

    def test_optimal_respects_ruin_tolerance(self):
        rec = mc.optimal_risk_fraction(0.55, 1.5, 1.0, ruin_tolerance=0.01,
                                       n_paths=800, n_trades=150)
        chosen = [s for s in rec.sweep if s.risk_fraction == rec.recommended_fraction][0]
        self.assertLessEqual(chosen.prob_ruin, 0.01)
        self.assertLessEqual(rec.recommended_fraction, 0.025)  # hard cap

    def test_overbetting_reduces_growth(self):
        # past the optimum, median terminal wealth should fall (geometric penalty)
        modest = mc.simulate(0.55, 1.5, 1.0, 0.02, n_paths=1500, n_trades=250)
        reckless = mc.simulate(0.55, 1.5, 1.0, 0.20, n_paths=1500, n_trades=250)
        self.assertGreater(modest.median_terminal, reckless.median_terminal)


# --------------------------------------------------------------------------- #
# ADAPTIVE RISK GOVERNOR                                                       #
# --------------------------------------------------------------------------- #
class TestAdaptiveRisk(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.gov = AdaptiveRiskGovernor(self.cfg)

    def proven(self, **kw):
        d = dict(n_trades=100, win_rate=0.55, avg_win_dollars=1.5, avg_loss_dollars=1.0)
        d.update(kw)
        return StrategyStats(**d)

    def test_risk_within_bounds(self):
        ctx = RiskContext(stats=self.proven(), n_proven_trades=100,
                          ruin_recommended_fraction=0.015)
        d = self.gov.decide(ctx)
        self.assertGreaterEqual(d.fraction, self.cfg["adaptive_risk"]["floor_pct"])
        self.assertLessEqual(d.fraction, self.cfg["adaptive_risk"]["absolute_max_pct"])

    def test_drawdown_throttles_risk_down(self):
        full = RiskContext(stats=self.proven(), drawdown_from_ath=0.0,
                           n_proven_trades=100, ruin_recommended_fraction=0.015)
        deep = RiskContext(stats=self.proven(), drawdown_from_ath=0.15,
                           n_proven_trades=100, ruin_recommended_fraction=0.015)
        self.assertGreater(self.gov.decide(full).fraction,
                           self.gov.decide(deep).fraction)

    def test_full_drawdown_goes_to_floor(self):
        ctx = RiskContext(stats=self.proven(), drawdown_from_ath=0.20,
                          n_proven_trades=100, ruin_recommended_fraction=0.015)
        self.assertEqual(self.gov.decide(ctx).fraction,
                         self.cfg["adaptive_risk"]["floor_pct"])

    def test_unproven_cannot_exceed_nominal(self):
        ctx = RiskContext(stats=self.proven(n_trades=10), n_proven_trades=10,
                          ruin_recommended_fraction=0.025)
        self.assertLessEqual(self.gov.decide(ctx).fraction,
                             self.cfg["adaptive_risk"]["nominal_pct"] + 1e-9)

    def test_proven_edge_scales_above_brief_1_5pct(self):
        # the coupling fix: a strong PROVEN edge must be allowed to exceed 1.5%,
        # up to the 2.5% absolute ceiling. Kelly here is large; ruin cap 2.5%.
        ctx = RiskContext(stats=self.proven(win_rate=0.60, avg_win_dollars=2.0),
                          drawdown_from_ath=0.0, realized_vol_20d=0.12,
                          n_proven_trades=200, ruin_recommended_fraction=0.025)
        f = self.gov.decide(ctx).fraction
        self.assertGreater(f, self.cfg["risk"]["per_trade_risk_pct"])   # > 1.5%
        self.assertLessEqual(f, self.cfg["adaptive_risk"]["absolute_max_pct"])  # <= 2.5%

    def test_never_exceeds_absolute_ceiling(self):
        # even with an insane ruin recommendation, clamp at 2.5%
        ctx = RiskContext(stats=self.proven(win_rate=0.70, avg_win_dollars=3.0),
                          n_proven_trades=500, ruin_recommended_fraction=0.99)
        self.assertLessEqual(self.gov.decide(ctx).fraction,
                             self.cfg["adaptive_risk"]["absolute_max_pct"] + 1e-9)

    def test_high_vol_throttles_down(self):
        calm = RiskContext(stats=self.proven(), realized_vol_20d=0.10,
                           n_proven_trades=100, ruin_recommended_fraction=0.015)
        storm = RiskContext(stats=self.proven(), realized_vol_20d=0.40,
                            n_proven_trades=100, ruin_recommended_fraction=0.015)
        self.assertGreater(self.gov.decide(calm).fraction,
                           self.gov.decide(storm).fraction)


if __name__ == "__main__":
    unittest.main()
