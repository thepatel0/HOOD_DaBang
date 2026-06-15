import copy
import unittest

from src import config


class TestConfig(unittest.TestCase):
    def test_loads_and_validates(self):
        cfg = config.load()
        self.assertEqual(cfg["account"]["starting_capital_usd"], 1500)

    def test_scorecard_weights_sum_to_one(self):
        cfg = config.load()
        w = cfg["conviction"]["scorecard_weights"]
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_verdict_weights_sum_to_one(self):
        cfg = config.load()
        w = cfg["conviction"]["verdict_weights"]
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_rejects_bad_scorecard_weights(self):
        bad = copy.deepcopy(config.DEFAULTS)
        bad["conviction"]["scorecard_weights"]["setup_quality"] = 0.99
        with self.assertRaises(config.ConfigError):
            config.validate(bad)

    def test_rejects_execution_floor_below_stage1(self):
        bad = copy.deepcopy(config.DEFAULTS)
        bad["conviction"]["execution_floor"] = 64
        with self.assertRaises(config.ConfigError):
            config.validate(bad)

    def test_rejects_ramp_above_capital(self):
        bad = copy.deepcopy(config.DEFAULTS)
        bad["capital_ramp"]["live_day_31_plus_usd"] = 99999
        with self.assertRaises(config.ConfigError):
            config.validate(bad)


if __name__ == "__main__":
    unittest.main()
