import unittest

from src import db
from src.journal import Journal
from src.knowledge.base import KnowledgeBase
from src.research.paper_loop import PaperLearningLoop


class TestKnowledgeBase(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase(":memory:")

    def test_validates_real_edge(self):
        treatment = [0.6] * 40 + [-0.2] * 20   # clear positive edge
        control = [0.0] * 60
        p = self.kb.validate_and_store("orb@bull_trend_low_vol", "orb edge",
                                       treatment, control)
        self.assertIsNotNone(p)
        self.assertEqual(p.status, "validated")
        self.assertEqual(p.source, "paper")

    def test_rejects_noise(self):
        treatment = [0.1, -0.1] * 30
        control = [0.1, -0.1] * 30
        p = self.kb.validate_and_store("orb@range", "no edge", treatment, control)
        self.assertIsNone(p)                    # noise never enters the KB

    def test_insufficient_sample_rejected(self):
        p = self.kb.validate_and_store("x@y", "tiny", [0.5] * 5, [0.0] * 5)
        self.assertIsNone(p)

    def test_validated_patterns_listed(self):
        self.kb.validate_and_store("orb@bull_trend_low_vol", "edge",
                                   [0.6] * 40 + [-0.2] * 20, [0.0] * 60)
        self.assertEqual(len(self.kb.validated_patterns()), 1)

    def test_conviction_tilt_bounded(self):
        self.kb.validate_and_store("orb@bull_trend_low_vol", "edge",
                                   [2.0] * 40, [0.0] * 40)   # huge edge
        tilt = self.kb.conviction_tilt("orb", "bull_trend_low_vol")
        self.assertLessEqual(tilt, 5.0)          # bounded — can't dominate bedrock
        self.assertGreater(tilt, 0)

    def test_no_tilt_without_knowledge(self):
        self.assertEqual(self.kb.conviction_tilt("orb", "crisis"), 0.0)

    def test_retire(self):
        self.kb.validate_and_store("orb@x", "edge", [0.6] * 40, [0.0] * 40)
        self.kb.retire("orb@x")
        self.assertEqual(len(self.kb.validated_patterns()), 0)


class TestPaperLearningLoop(unittest.TestCase):
    def setUp(self):
        self.paper_journal = Journal(db.init_db(":memory:"))   # ISOLATED paper DB
        self.kb = KnowledgeBase(":memory:")
        self.loop = PaperLearningLoop(self.paper_journal, self.kb, min_sample=20)

    def _seed(self, strategy, regime, r, n):
        for i in range(n):
            tid = self.paper_journal.record_trade(
                ticker="X", strategy=strategy, strategy_version="1.0.0", side="long",
                entry_ts="t", entry_price=100, entry_shares=1, stop_price=99,
                conviction_score=80, thesis_id="th", market_regime=regime,
                order_id=f"{strategy}-{regime}-{i}")
            self.paper_journal.close_trade(tid, exit_ts="t", exit_price=101,
                                           exit_reason="target", pnl_dollars=r, pnl_r=r)

    def test_learns_and_validates(self):
        self._seed("orb", "bull_trend_low_vol", 0.5, 30)   # strong segment
        self._seed("vwap_reversion", "range_high_vol", -0.3, 30)  # weak
        report = self.loop.learn()
        self.assertEqual(report.n_paper_trades, 60)
        # the strong segment validates; the weak one doesn't
        segs = [p.segment for p in report.validated]
        self.assertIn("orb@bull_trend_low_vol", segs)
        self.assertNotIn("vwap_reversion@range_high_vol", segs)

    def test_validated_knowledge_has_paper_provenance(self):
        self._seed("orb", "bull_trend_low_vol", 0.5, 30)
        self.loop.learn()
        for p in self.kb.validated_patterns():
            self.assertEqual(p.source, "paper")

    def test_ab_test_adopts_better_variant(self):
        ab = self.loop.ab_test("orb_v1", [0.2] * 40, "orb_v2", [0.7] * 40)
        self.assertEqual(ab.winner, "orb_v2")
        self.assertTrue(ab.adopt)

    def test_ab_test_keeps_incumbent_on_tie(self):
        ab = self.loop.ab_test("orb_v1", [0.3] * 40, "orb_v2", [0.3] * 40)
        self.assertEqual(ab.winner, "orb_v1")    # challenger must prove it
        self.assertFalse(ab.adopt)

    def test_isolation_paper_journal_separate(self):
        # the loop only ever reads its (paper) journal; never a production handle
        self._seed("orb", "bull_trend_low_vol", 0.5, 25)
        self.assertEqual(len(self.loop._paper_trades()), 25)


if __name__ == "__main__":
    unittest.main()
