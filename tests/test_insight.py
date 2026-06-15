import json
import unittest
from datetime import datetime, timezone

from src import config, db
from src.strategies.base import Setup, MarketState
from src.insight.thesis import Thesis
from src.insight.engine import InsightEngine
from src.llm_budget import LLMBudget
from src.llm_client import LLMClient, MockLLMTransport


def orb_setup():
    return Setup(
        ticker="AAPL", strategy="orb", version="1.0.0", side="long",
        entry_price=101.5, stop_price=99.9, targets=[(103.9, 0.5)],
        factors={"setup_quality": 80, "regime_fit": 75, "multi_timeframe_confluence": 70,
                 "volume_confirmation": 85, "catalyst_freshness": 60,
                 "liquidity_spread": 90, "risk_reward_geometry": 70,
                 "strategy_recent_expectancy": 55},
        expected_hold_min=90)


def ms():
    m = MarketState(ticker="AAPL", now_et="2026-06-15T09:42:00-04:00", quote=101.5,
                    regime="bull_trend_low_vol", rvol=2.5)
    m.vwap = 100.9
    m.opening_range_high = 101.0
    m.opening_range_low = 100.0
    return m


class TestThesis(unittest.TestCase):
    def test_falsifiable_requires_mechanism_and_invalidation(self):
        t = Thesis("AAPL", "long", "claim", "real mechanism", ["loses stop"])
        self.assertTrue(t.is_falsifiable)

    def test_no_mechanism_not_falsifiable(self):
        t = Thesis("AAPL", "long", "claim", "   ", ["loses stop"])
        self.assertFalse(t.is_falsifiable)

    def test_no_invalidation_not_falsifiable(self):
        t = Thesis("AAPL", "long", "claim", "mechanism", [])
        self.assertFalse(t.is_falsifiable)

    def test_confidence_base_rate_gap(self):
        t = Thesis("AAPL", "long", "c", "m", ["x"], confidence=0.8, base_rate=0.5)
        self.assertAlmostEqual(t.confidence_base_rate_gap, 0.3)

    def test_id_stable(self):
        t1 = Thesis("AAPL", "long", "c", "m", ["x"])
        t2 = Thesis("AAPL", "long", "c", "m", ["y"])
        self.assertEqual(t1.id(), t2.id())  # id keyed on claim+mechanism


class TestInsightEngineDeterministic(unittest.TestCase):
    def setUp(self):
        self.eng = InsightEngine(config.load())

    def test_builds_falsifiable_thesis(self):
        t = self.eng.build(orb_setup(), ms())
        self.assertIsNotNone(t)
        self.assertTrue(t.is_falsifiable)
        self.assertIn("Overnight information", t.mechanism)

    def test_invalidation_includes_stop_and_vwap(self):
        t = self.eng.build(orb_setup(), ms())
        joined = " ".join(t.invalidation)
        self.assertIn("99.9", joined)       # stop
        self.assertIn("VWAP", joined)        # vwap loss
        self.assertIn("opening range", joined)

    def test_base_rate_set(self):
        t = self.eng.build(orb_setup(), ms())
        self.assertEqual(t.base_rate, 0.50)  # orb default

    def test_base_rate_override(self):
        eng = InsightEngine(config.load(), base_rates={"orb": 0.61})
        t = eng.build(orb_setup(), ms())
        self.assertEqual(t.base_rate, 0.61)

    def test_drivers_only_strong_factors(self):
        t = self.eng.build(orb_setup(), ms())
        # only factors >= 60 become drivers
        self.assertTrue(all(d.weight >= 0.6 for d in t.drivers))


class TestInsightEngineLLM(unittest.TestCase):
    def _client(self, text):
        budget = LLMBudget(db.init_ledger(":memory:"), config.load(),
                           now=lambda: datetime(2026, 6, 15, tzinfo=timezone.utc))
        return LLMClient(config.load(), budget, MockLLMTransport(text=text))

    def test_llm_valid_json_thesis(self):
        payload = json.dumps({"claim": "AMD to 103", "mechanism": "real causal reason",
                              "invalidation": ["loses 100"], "expected_path": "up",
                              "confidence": 0.7})
        eng = InsightEngine(config.load(), llm_client=self._client(payload))
        t = eng.build(orb_setup(), ms(), use_llm=True)
        self.assertEqual(t.claim, "AMD to 103")
        self.assertEqual(t.confidence, 0.7)

    def test_llm_pass_falls_back_to_deterministic(self):
        eng = InsightEngine(config.load(), llm_client=self._client('{"pass": true}'))
        t = eng.build(orb_setup(), ms(), use_llm=True)
        self.assertIsNotNone(t)                    # fell back
        self.assertIn("Overnight information", t.mechanism)

    def test_llm_bad_json_falls_back(self):
        eng = InsightEngine(config.load(), llm_client=self._client("not json"))
        t = eng.build(orb_setup(), ms(), use_llm=True)
        self.assertIsNotNone(t)
        self.assertTrue(t.is_falsifiable)


if __name__ == "__main__":
    unittest.main()
