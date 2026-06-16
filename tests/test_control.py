import os
import tempfile
import unittest

from src import config, db
from src.operator.environment import RunEnvironment
from src.operator.control import ControlPlane
from src.operator.commands import CommandRouter
from src.journal import Journal
from src.strategies.all import build_full_registry
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.execution import ExecutionHandler
from src.controller import Controller


class TestEnvironmentIsolation(unittest.TestCase):
    def test_paper_and_prod_separate(self):
        prod = RunEnvironment.production("/data")
        paper = RunEnvironment.paper("/data")
        self.assertNotEqual(prod.db_path, paper.db_path)
        self.assertNotEqual(prod.memory_dir, paper.memory_dir)
        self.assertTrue(paper.is_paper)
        self.assertFalse(prod.is_paper)

    def test_isolation_assert_passes_for_distinct(self):
        prod = RunEnvironment.production("/data")
        paper = RunEnvironment.paper("/data")
        prod.assert_isolated_from(paper)   # no raise

    def test_isolation_assert_raises_for_same_root(self):
        a = RunEnvironment("production", "/x")
        b = RunEnvironment("paper", "/x")
        with self.assertRaises(RuntimeError):
            a.assert_isolated_from(b)


class TestControlPlane(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.join(tempfile.mkdtemp(), "control.json")
        # eligibility: not eligible by default
        self.cp = ControlPlane(self.tmp, eligibility_check=lambda: (False, ["no proven strategy"]))

    def test_starts_off(self):
        self.assertEqual(self.cp.execution_mode(), "OFF")

    def test_app_on_then_research_recommends(self):
        self.cp.app(True)
        self.cp.research(True)
        self.assertEqual(self.cp.execution_mode(), "RECOMMEND")

    def test_app_idle_when_research_off(self):
        self.cp.app(True)
        self.assertEqual(self.cp.execution_mode(), "IDLE")

    def test_paper_mode(self):
        self.cp.app(True)
        self.cp.paper(True)
        self.assertEqual(self.cp.execution_mode(), "PAPER")
        self.assertTrue(self.cp.state.research)   # paper implies research

    def test_research_off_blocked_while_paper(self):
        self.cp.app(True); self.cp.paper(True)
        r = self.cp.research(False)
        self.assertFalse(r.ok)

    def test_app_off_kills_everything(self):
        self.cp.app(True); self.cp.paper(True)
        self.cp.app(False)
        self.assertEqual(self.cp.execution_mode(), "OFF")
        self.assertFalse(self.cp.state.paper)

    def test_live_requires_arm_and_eligibility(self):
        self.cp.app(True); self.cp.research(True)
        r = self.cp.trading(True)
        self.assertFalse(r.ok)                     # not armed
        arm = self.cp.arm_trading()
        self.assertFalse(arm.ok)                   # not eligible
        self.assertIn("no proven strategy", arm.blockers)

    def test_live_path_when_eligible(self):
        cp = ControlPlane(self.tmp, eligibility_check=lambda: (True, []))
        cp.app(True); cp.research(True)
        self.assertTrue(cp.arm_trading().ok)
        r = cp.trading(True)
        self.assertTrue(r.ok)
        self.assertEqual(cp.execution_mode(), "LIVE")

    def test_persistence(self):
        self.cp.app(True); self.cp.research(True)
        cp2 = ControlPlane(self.tmp)
        self.assertEqual(cp2.execution_mode(), "RECOMMEND")


def orb_win_bars():
    from src.strategies.base import Bar
    def ts(i): return f"2026-06-15T{9 + (30 + i)//60:02d}:{(30 + i)%60:02d}:00-04:00"
    bars = [Bar(ts(i), 100.4, 101.0, 100.0, 100.5, 2000) for i in range(5)]
    bars += [Bar(ts(i), 100.5, 100.9, 100.2, 100.6, 1500) for i in range(5, 12)]
    bars.append(Bar(ts(12), 100.7, 101.6, 100.6, 101.5, 12000))
    bars.append(Bar(ts(13), 101.5, 110.0, 101.4, 108.0, 15000))
    bars += [Bar(ts(i), 100.5, 100.8, 100.3, 100.5, 1200) for i in range(14, 40)]
    return bars


class TestRecommendMode(unittest.TestCase):
    def _ctrl(self, execution_mode):
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
                          execution_mode=execution_mode)
        ctrl.start_session(equity=1500.0)
        return ctrl, journal

    def _run(self, ctrl):
        from src.analysts_local.technical import TechnicalAnalyst
        ta = TechnicalAnalyst()
        bars = orb_win_bars()
        for i in range(10, len(bars)):
            ms = ta.compute("AAPL", bars[i].ts, bars[i].c, {"1m": bars[:i+1]},
                            prior_close=100.0, regime="bull_trend_low_vol",
                            has_catalyst=True, catalyst_age_min=5, catalyst_sources=2,
                            adv_shares=5_000_000)
            ctrl.process_tick({"AAPL": ms}, bars[i].ts)

    def test_recommend_mode_writes_recommendation_no_trade(self):
        ctrl, journal = self._ctrl("recommend")
        self._run(ctrl)
        self.assertGreaterEqual(ctrl.recommendations_today, 1)
        self.assertEqual(len(journal.closed_trades()), 0)    # NO trades executed
        recs = journal.recent_recommendations()
        self.assertGreaterEqual(len(recs), 1)
        self.assertEqual(recs[0]["ticker"], "AAPL")

    def test_execute_mode_trades(self):
        ctrl, journal = self._ctrl("execute")
        self._run(ctrl)
        self.assertGreaterEqual(len(journal.closed_trades()), 1)
        self.assertEqual(ctrl.recommendations_today, 0)


class TestControlCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.join(tempfile.mkdtemp(), "c.json")
        self.cp = ControlPlane(self.tmp, eligibility_check=lambda: (False, ["unproven"]))
        self.journal = Journal(db.init_db(":memory:"))
        self.router = CommandRouter(journal=self.journal, registry=build_full_registry(),
                                    control=self.cp)

    def test_app_on(self):
        out = self.router.dispatch("/app on")
        self.assertIn("ON", out)

    def test_research_on_recommends(self):
        self.router.dispatch("/app on")
        self.router.dispatch("/research on")
        self.assertIn("RECOMMEND", self.router.dispatch("/mode"))

    def test_trading_blocked_with_blockers(self):
        self.router.dispatch("/app on")
        self.router.dispatch("/research on")
        out = self.router.dispatch("/trading on")
        self.assertIn("not armed", out)

    def test_trading_arm_shows_eligibility_blockers(self):
        self.router.dispatch("/app on")
        out = self.router.dispatch("/trading arm")
        self.assertIn("unproven", out)

    def test_paper_on(self):
        self.router.dispatch("/app on")
        self.assertIn("isolated sandbox", self.router.dispatch("/paper on"))

    def test_recommendations_empty(self):
        self.assertIn("no recommendations", self.router.dispatch("/recommendations"))


if __name__ == "__main__":
    unittest.main()
