import unittest

from src import config, db
from src.research.news_classifier import classify_headline, aggregate
from src.research.regime_features import (compute_features, detect_regime,
                                          realized_vol_annualized, compute_breadth)
from src.operator.eligibility import live_eligibility
from src.strategies.all import build_full_registry
from src.strategies.registry import FIVE_GATES
from src.strategies.base import Bar
from src.research.runner import ResearchRunner
from src.data_feeds.bars import CachedBarFeed, FeedResult


class TestNewsClassifier(unittest.TestCase):
    def test_ma_bullish(self):
        c = classify_headline("Acme to acquire Beta Corp in $5B deal")
        self.assertEqual(c.category, "M&A")
        self.assertEqual(c.direction, "bull")
        self.assertTrue(c.is_catalyst)

    def test_guidance_cut_bearish(self):
        c = classify_headline("XYZ cuts guidance, warns on demand")
        self.assertEqual(c.direction, "bear")

    def test_noise(self):
        c = classify_headline("Company announces new office location")
        self.assertEqual(c.category, "noise")
        self.assertFalse(c.is_catalyst)

    def test_aggregate_net_direction(self):
        ctx = aggregate(["Acme beats earnings, raises guidance",
                         "Acme upgraded to buy"])
        self.assertTrue(ctx.has_catalyst)
        self.assertEqual(ctx.direction, "bull")
        self.assertGreaterEqual(ctx.sources, 1)

    def test_aggregate_no_catalyst(self):
        self.assertFalse(aggregate(["random news", "more noise"]).has_catalyst)


class TestRegimeFeatures(unittest.TestCase):
    def _spy(self, trend="up"):
        bars = []
        for i in range(220):
            price = 400 + (i * 0.5 if trend == "up" else -i * 0.2)
            bars.append(Bar(f"d{i}", price, price + 1, price - 1, price, 1e6))
        return bars

    def test_compute_features_uptrend(self):
        f = compute_features(self._spy("up"), vix=14, breadth=0.7)
        self.assertGreater(f.trend_50, 0)
        self.assertEqual(len(f.as_vector()), 5)

    def test_detect_regime_bull(self):
        regime = detect_regime(self._spy("up"), vix=14, breadth=0.7)
        self.assertIn("bull", regime)

    def test_detect_regime_insufficient_data(self):
        self.assertEqual(detect_regime([Bar("d", 400, 401, 399, 400, 1e6)]), "transitional")

    def test_realized_vol(self):
        flat = [Bar(f"d{i}", 100, 100, 100, 100, 1e6) for i in range(30)]
        self.assertEqual(realized_vol_annualized([b.c for b in flat]), 0.0)

    def test_breadth(self):
        up = [Bar(f"d{i}", 100 + i, 100 + i, 99 + i, 100 + i, 1e6) for i in range(60)]
        down = [Bar(f"d{i}", 200 - i, 201 - i, 199 - i, 200 - i, 1e6) for i in range(60)]
        b = compute_breadth({"A": up, "B": down})
        self.assertTrue(0 <= b <= 1)


class TestEligibility(unittest.TestCase):
    def test_blocked_without_gate_passers(self):
        reg = build_full_registry()
        ok, blockers = live_eligibility(reg, paper_trades=50, paper_expectancy_r=0.2)
        self.assertFalse(ok)
        self.assertTrue(any("five validation gates" in b for b in blockers))

    def test_eligible_when_all_met(self):
        reg = build_full_registry()
        for g in FIVE_GATES:
            reg.set_gate("orb", g, True)
        reg.promote("orb", "live")
        ok, blockers = live_eligibility(reg, paper_trades=50, paper_expectancy_r=0.2,
                                        self_tests_green=True, dod_overrides=True)
        self.assertTrue(ok, blockers)

    def test_short_paper_period_blocks(self):
        reg = build_full_registry()
        for g in FIVE_GATES:
            reg.set_gate("orb", g, True)
        reg.promote("orb", "live")
        ok, blockers = live_eligibility(reg, paper_trades=5, dod_overrides=True)
        self.assertFalse(ok)
        self.assertTrue(any("paper forward period" in b for b in blockers))


class FakeBarFeed:
    def __init__(self, bars_by_ticker):
        self.bars_by_ticker = bars_by_ticker

    def get_bars(self, ticker, interval="1d", lookback_days=5):
        return FeedResult(self.bars_by_ticker.get(ticker, []), from_cache=False)


class FakeController:
    def __init__(self):
        self.recommendations_today = 0
        self.ticks = []
        class S: trades_today = 0
        self.state = S()

    def process_tick(self, states, now_et):
        self.ticks.append(states)
        self.recommendations_today += len(states)   # pretend each name -> a rec


class TestResearchRunner(unittest.TestCase):
    def _spy(self):
        return [Bar(f"d{i}", 400 + i * 0.5, 401 + i * 0.5, 399 + i * 0.5, 400 + i * 0.5, 1e6)
                for i in range(220)]

    def _intraday(self):
        return [Bar(f"2026-06-15T09:{30+i:02d}:00-04:00", 100, 100.5, 99.5, 100, 2000)
                for i in range(40)]

    def test_detects_regime_and_builds_states(self):
        feed = FakeBarFeed({"SPY": self._spy(), "AAPL": self._intraday(),
                            "MSFT": self._intraday()})
        ctrl = FakeController()
        runner = ResearchRunner(feed, ctrl)
        summary = runner.run(["AAPL", "MSFT"], "2026-06-15T09:50:00-04:00",
                             vix=14, breadth=0.7)
        self.assertIn("bull", summary.regime)
        self.assertEqual(summary.states_built, 2)
        self.assertEqual(summary.recommendations, 2)

    def test_skips_names_without_data(self):
        feed = FakeBarFeed({"SPY": self._spy(), "AAPL": self._intraday()})  # no MSFT
        ctrl = FakeController()
        runner = ResearchRunner(feed, ctrl)
        summary = runner.run(["AAPL", "MSFT"], "2026-06-15T09:50:00-04:00")
        self.assertEqual(summary.states_built, 1)


if __name__ == "__main__":
    unittest.main()
