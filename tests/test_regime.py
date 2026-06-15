import time
import unittest

import numpy as np

from src.analysts_local.regime import (
    RegimeClassifier, deterministic_regime, LABELS,
)


def synth_dataset(seed=0, per=120):
    """Well-separated synthetic clusters across regimes."""
    rng = np.random.default_rng(seed)
    rows = []
    specs = {
        "bull_low":  ([0.05, 0.04, 0.10, 14, 0.70], 0.01),
        "bull_high": ([0.05, 0.04, 0.25, 24, 0.60], 0.01),
        "bear_high": ([-0.05, -0.04, 0.28, 28, 0.30], 0.01),
        "range_low": ([0.00, 0.00, 0.10, 14, 0.50], 0.005),
        "range_high":([0.00, 0.00, 0.22, 22, 0.50], 0.005),
        "crisis":    ([-0.06, -0.05, 0.50, 45, 0.20], 0.01),
    }
    for center, jit in specs.values():
        c = np.array(center)
        for _ in range(per):
            rows.append(c + rng.normal(0, 1, 5) * np.array([jit, jit, jit, 1.0, jit]))
    X = np.array(rows)
    rng.shuffle(X)
    return X


class TestDeterministicRegime(unittest.TestCase):
    def test_bull_low_vol(self):
        self.assertEqual(deterministic_regime(0.05, 0.04, 0.10, 14, 0.7),
                         "bull_trend_low_vol")

    def test_bear_high_vol(self):
        self.assertEqual(deterministic_regime(-0.05, -0.04, 0.25, 28, 0.3),
                         "bear_trend_high_vol")

    def test_range_low_vol(self):
        self.assertEqual(deterministic_regime(0.0, 0.0, 0.10, 14, 0.5),
                         "range_low_vol")

    def test_crisis_on_high_vol(self):
        self.assertEqual(deterministic_regime(0.0, 0.0, 0.50, 20, 0.5), "crisis")

    def test_crisis_on_high_vix(self):
        self.assertEqual(deterministic_regime(0.01, 0.01, 0.20, 40, 0.5), "crisis")

    def test_all_outputs_are_valid_labels(self):
        for f in [(0.05,0.04,0.1,14,0.7), (-0.05,-0.04,0.3,30,0.3), (0,0,0.1,14,0.5)]:
            self.assertIn(deterministic_regime(*f), LABELS)


class TestRegimeClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.X = synth_dataset()
        cls.clf = RegimeClassifier(n_states=6, seed=1).fit(cls.X)

    def test_unfitted_falls_back_to_deterministic(self):
        clf = RegimeClassifier()
        r = clf.classify([0.05, 0.04, 0.10, 14, 0.70])
        self.assertEqual(r.label, "bull_trend_low_vol")

    def test_clear_bull_classified(self):
        r = self.clf.classify([0.05, 0.04, 0.10, 14, 0.70])
        # both models should recognize a textbook bull-low-vol point
        self.assertEqual(r.rf_label, "bull_trend_low_vol")
        self.assertIn(r.label, ["bull_trend_low_vol", "transitional"])

    def test_crisis_classified(self):
        r = self.clf.classify([-0.06, -0.05, 0.50, 45, 0.20])
        self.assertEqual(r.rf_label, "crisis")

    def test_confidence_higher_when_agree(self):
        r = self.clf.classify([0.05, 0.04, 0.10, 14, 0.70])
        if r.agree:
            self.assertGreater(r.confidence, 0.7)
        else:
            self.assertEqual(r.label, "transitional")

    def test_residual_tracking_and_retrain(self):
        clf = RegimeClassifier()
        for _ in range(25):
            clf.record_outcome("bull_trend_low_vol", "bear_trend_high_vol")  # all wrong
        self.assertGreater(clf.residual_rate(), 0.9)
        self.assertTrue(clf.should_retrain())

    def test_no_retrain_when_accurate(self):
        clf = RegimeClassifier()
        for _ in range(25):
            clf.record_outcome("bull_trend_low_vol", "bull_trend_low_vol")
        self.assertFalse(clf.should_retrain())

    def test_latency_under_500ms(self):
        t0 = time.perf_counter()
        for _ in range(50):
            self.clf.classify([0.05, 0.04, 0.10, 14, 0.70])
        avg_ms = (time.perf_counter() - t0) / 50 * 1000
        self.assertLess(avg_ms, 500)


if __name__ == "__main__":
    unittest.main()
