import shutil
import tempfile
import unittest

from src import config
from src.app import Application
from src.strategies.base import Bar
from src.data_feeds.bars import FeedResult
from src.data_feeds.news_rss import NewsResult, Headline
from src.knowledge.base import KnowledgeBase
from src.controller import Controller
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.execution import ExecutionHandler
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.journal import Journal
from src import db
from src.strategies.all import build_full_registry


# --------------------------------------------------------------------------- #
# fakes (mirror test_research_runner / test_control patterns)                  #
# --------------------------------------------------------------------------- #
def _ts(i):
    return f"2026-06-15T{9 + (30 + i)//60:02d}:{(30 + i)%60:02d}:00-04:00"


def orb_breakout_now():
    """ORB long whose breakout is the LAST 1m bar (so the runner's single-shot
    build_state -> scan fires), inside the 09:35-10:00 entry window, >=30 bars."""
    bars = [Bar(_ts(i), 100.4, 101.0, 100.0, 100.5, 2000) for i in range(5)]      # OR 100-101
    bars += [Bar(_ts(i), 100.5, 100.9, 100.2, 100.6, 1500) for i in range(5, 29)]  # quiet
    bars.append(Bar(_ts(29), 100.7, 103.0, 100.6, 102.5, 20000))                   # breakout (last)
    return bars


def spy_uptrend():
    return [Bar(f"d{i}", 400 + i * 0.5, 401 + i * 0.5, 399 + i * 0.5, 400 + i * 0.5, 1e6)
            for i in range(220)]


class FakeBarFeed:
    def __init__(self, bars_by_ticker):
        self.bars_by_ticker = bars_by_ticker

    def get_bars(self, ticker, interval="1d", lookback_days=5):
        return FeedResult(self.bars_by_ticker.get(ticker, []), from_cache=False)


class FakeNewsFeed:
    """Returns a catalyst headline so the ORB precondition is met deterministically."""
    def fetch(self, ticker, only_new=True):
        return NewsResult([Headline("Acme to acquire Beta Corp in $5B deal",
                                    "link", "pub", "hash", ticker)])


def _app(tmp):
    feed = FakeBarFeed({"SPY": spy_uptrend(), "AAPL": orb_breakout_now()})
    return Application(config.load(), tmp, bar_feed=feed, news_feed=FakeNewsFeed())


class TestApplicationIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_builds_with_isolated_environments(self):
        app = _app(self.tmp)
        # separate roots / db files — the operator's hard isolation requirement
        self.assertNotEqual(app.prod_env.db_path, app.paper_env.db_path)
        self.assertNotEqual(app.prod_env.root, app.paper_env.root)
        self.assertIsNot(app.prod_journal, app.paper_journal)
        # both controllers share the ONE knowledge base (the only bridge)
        self.assertIs(app.prod_controller.knowledge_base, app.knowledge)
        self.assertIs(app.paper_controller.knowledge_base, app.knowledge)

    def test_status_reflects_control_mode(self):
        app = _app(self.tmp)
        self.assertEqual(app.status()["mode"], "OFF")
        app.control.app(True)
        self.assertEqual(app.status()["mode"], "IDLE")
        app.control.research(True)
        st = app.status()
        self.assertEqual(st["mode"], "RECOMMEND")
        self.assertTrue(st["app"])
        self.assertTrue(st["research"])

    def test_idle_modes_do_nothing(self):
        app = _app(self.tmp)
        # OFF
        summary = app.research_cycle(["AAPL"], _ts(29))
        self.assertEqual(summary.recommendations, 0)
        self.assertEqual(summary.states_built, 0)
        # app on but research off -> IDLE
        app.control.app(True)
        summary = app.research_cycle(["AAPL"], _ts(29))
        self.assertEqual(summary.recommendations, 0)


class TestResearchRecommendMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_recommend_writes_to_prod_journal_no_trades(self):
        app = _app(self.tmp)
        app.control.app(True)
        app.control.research(True)            # -> RECOMMEND
        summary = app.research_cycle(["AAPL"], _ts(29))
        self.assertEqual(summary.recommendations, 1)
        # recommendation landed in the PRODUCTION journal
        recs = app.prod_journal.recent_recommendations(100)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["ticker"], "AAPL")
        # NO orders placed in either environment
        self.assertEqual(len(app.prod_journal.closed_trades()), 0)
        self.assertEqual(len(app.prod_controller.open), 0)
        # the paper environment is completely untouched
        self.assertEqual(len(app.paper_journal.recent_recommendations(100)), 0)
        self.assertEqual(len(app.paper_journal.closed_trades()), 0)


class TestPaperCycleIsolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_paper_cycle_executes_and_learns_prod_untouched(self):
        app = _app(self.tmp)
        app.control.app(True)
        app.control.paper(True)               # -> PAPER
        summary, report = app.paper_cycle(["AAPL"], _ts(29))
        # the paper controller executed (opened a position in the sandbox)
        self.assertEqual(summary.recommendations, 0)   # execute mode, not recommend
        self.assertEqual(len(app.paper_controller.open), 1)
        # the learning loop ran over the isolated paper journal
        self.assertEqual(report.n_paper_trades, 0)     # none closed yet, loop still ran
        self.assertIn("paper trades", report.notes)
        # production journal is entirely untouched (true isolation)
        self.assertEqual(len(app.prod_journal.closed_trades()), 0)
        self.assertEqual(len(app.prod_journal.recent_recommendations(100)), 0)
        self.assertEqual(len(app.prod_controller.open), 0)


class TestKnowledgeTilt(unittest.TestCase):
    """A validated positive pattern for (strategy, regime) raises conviction vs
    a controller with no knowledge base — the paper->production tilt path."""

    def _ctrl(self, knowledge):
        cfg = config.load()
        reg = build_full_registry(activation="paper")
        client = RobinhoodMCPClient(MockTransport({
            "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                      "filled_shares": p["shares"], "avg_fill_price": p["limit_price"]},
            "place_stop_order": lambda p: {"order_id": p["client_order_id"], "status": "accepted",
                                           "filled_shares": 0, "avg_fill_price": 0.0},
            "cancel_order": {}, "get_positions": {"positions": []}}))
        journal = Journal(db.init_db(":memory:"))
        ctrl = Controller(cfg, reg, ConvictionGate(cfg), InsightEngine(cfg),
                          AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                          ExecutionHandler(client, cfg), journal, mode="rules",
                          execution_mode="recommend", knowledge_base=knowledge)
        ctrl.start_session(equity=1500.0)
        return ctrl, journal

    def _run_and_conviction(self, ctrl, journal):
        from src.analysts_local.technical import TechnicalAnalyst
        ta = TechnicalAnalyst()
        bars = orb_breakout_now()
        ms = ta.compute("AAPL", bars[-1].ts, bars[-1].c, {"1m": bars},
                        prior_close=100.0, regime="bull_trend_low_vol",
                        has_catalyst=True, catalyst_age_min=5, catalyst_sources=2,
                        adv_shares=5_000_000)
        ctrl.process_tick({"AAPL": ms}, bars[-1].ts)
        recs = journal.recent_recommendations(1)
        self.assertTrue(recs, "expected a recommendation to be written")
        return recs[0]["conviction"]

    def test_validated_pattern_raises_conviction(self):
        # control: no knowledge base
        ctrl0, j0 = self._ctrl(None)
        conv_base = self._run_and_conviction(ctrl0, j0)

        # treatment: knowledge base with a validated positive edge for orb@regime
        kb = KnowledgeBase(":memory:")
        treatment = [1.0] * 40        # strong positive R-multiples
        control = [0.0] * 40
        kp = kb.validate_and_store("orb@bull_trend_low_vol",
                                   "orb has an edge in bull_trend_low_vol",
                                   treatment_samples=treatment, control_samples=control,
                                   source="paper", min_sample=30)
        self.assertIsNotNone(kp)                  # the pattern validated
        self.assertGreater(kb.conviction_tilt("orb", "bull_trend_low_vol"), 0.0)

        ctrl1, j1 = self._ctrl(kb)
        conv_tilted = self._run_and_conviction(ctrl1, j1)

        self.assertGreater(conv_tilted, conv_base)


if __name__ == "__main__":
    unittest.main()
