import unittest

from src import config
from src.conviction.gate import ConvictionGate
from src.conviction.scorecard import Signal


GOOD = {  # a textbook-clean confluence signal -> ~high score
    "setup_quality": 90, "regime_fit": 85, "multi_timeframe_confluence": 88,
    "volume_confirmation": 80, "catalyst_freshness": 75, "liquidity_spread": 90,
    "risk_reward_geometry": 85, "strategy_recent_expectancy": 70,
}
WEAK = {k: 30 for k in GOOD}  # strong on nothing -> dies below floor


def sig(ticker, factors, **kw):
    return Signal(ticker=ticker, strategy=kw.pop("strategy", "orb"),
                  side="long", factors=dict(factors), **kw)


class TestConvictionGate(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.gate = ConvictionGate(self.cfg)

    def test_top_1_to_3_advance_only(self):
        # 10 signals: 5 strong (varying), 5 weak. Exactly top 3 advance.
        signals = []
        for i in range(5):
            f = dict(GOOD)
            f["setup_quality"] = 90 - i * 3   # decreasing -> distinct ranks
            signals.append(sig(f"S{i}", f))
        for i in range(5):
            signals.append(sig(f"W{i}", WEAK))
        res = self.gate.stage1(signals)
        self.assertEqual(len(res.advancing), 3)
        advanced = [s.ticker for s in res.advancing]
        self.assertEqual(advanced, ["S0", "S1", "S2"])

    def test_weak_signal_dies_below_floor(self):
        res = self.gate.stage1([sig("W", WEAK)])
        self.assertEqual(len(res.advancing), 0)
        d = res.decisions[0]
        self.assertFalse(d.advanced)
        self.assertIn("below_stage1_floor", d.reason)

    def test_hard_floor_overrides_high_score(self):
        # perfect factors but spread too wide -> rejected regardless of score
        s = sig("X", GOOD, spread_pct=0.01)
        res = self.gate.stage1([s])
        self.assertEqual(len(res.advancing), 0)
        self.assertIn("hard_floor:spread_gt_0.3pct", res.decisions[0].reason)

    def test_crisis_regime_blocks_non_pairs(self):
        s = sig("X", GOOD, regime="crisis", strategy="orb")
        res = self.gate.stage1([s])
        self.assertEqual(len(res.advancing), 0)
        self.assertIn("crisis_regime_non_pairs", res.decisions[0].reason)

    def test_pairs_allowed_in_crisis(self):
        s = sig("X", GOOD, regime="crisis", strategy="pairs")
        res = self.gate.stage1([s])
        self.assertEqual(len(res.advancing), 1)

    def test_zero_shares_hard_floor(self):
        s = sig("X", GOOD, shares_at_risk_cap=0)
        res = self.gate.stage1([s])
        self.assertIn("hard_floor:zero_whole_shares_at_risk_cap",
                      res.decisions[0].reason)

    def test_highest_not_taken_reported(self):
        # one signal just below floor; gate surfaces it (dashboard requirement)
        f = dict(GOOD)
        f = {k: 60 for k in GOOD}  # ~60 < 65 floor
        res = self.gate.stage1([sig("AMD", f)])
        hnt = res.highest_not_taken
        self.assertIsNotNone(hnt)
        self.assertEqual(hnt.ticker, "AMD")

    def test_stage2_verdict_formula(self):
        # det 80, bull .8 bear .5 -> margin .3, thesis .7, calib .6 -> 65 (< floor)
        v = self.gate.stage2_verdict(80, 0.8, 0.5, 0.7, 0.6)
        expected = 0.45 * 80 + 0.20 * 30 + 0.20 * 70 + 0.15 * 60  # = 65.0
        self.assertAlmostEqual(v["final_conviction"], expected, places=4)
        self.assertFalse(v["passes"])  # 65 < 72: correctly demanding

    def test_stage2_high_conviction_passes(self):
        # strong across the board -> clears the 72 floor
        v = self.gate.stage2_verdict(92, 0.9, 0.3, 0.85, 0.8)
        self.assertGreaterEqual(v["final_conviction"], 72)
        self.assertTrue(v["passes"])

    def test_loss_cooldown_raises_floor(self):
        self.gate.set_floor_bump(5)  # revenge suppression
        v = self.gate.stage2_verdict(70, 0.7, 0.6, 0.6, 0.6)
        self.assertEqual(v["execution_floor"], 77)


if __name__ == "__main__":
    unittest.main()
