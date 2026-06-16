import unittest
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

from src import config, db
from src.journal import Journal
from src.strategies.all import build_full_registry
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.robinhood import RobinhoodAgenticAdapter
from src.execution import ExecutionHandler
from src.controller import Controller
from src.ops.orchestrator import AutonomousOrchestrator
from src.data_feeds.bars import FeedResult
from src.strategies.base import Bar
from tests.test_prod_guardrails import FakeRH


class FakeBarFeed:
    def __init__(self, bars_by_ticker):
        self.bars = bars_by_ticker

    def get_bars(self, ticker, interval="1d", lookback_days=5):
        return FeedResult(self.bars.get(ticker, []), from_cache=False)


def daily(n=220, base=400.0, up=True):
    return [Bar(f"d{i}", base + (i*0.5 if up else -i*0.2), base+1, base-1,
                base + (i*0.5 if up else -i*0.2), 1e6) for i in range(n)]


def intraday():
    return [Bar(f"2026-06-16T{9 + (30+i)//60:02d}:{(30+i)%60:02d}:00-04:00",
                100, 100.5, 99.5, 100, 2000) for i in range(40)]


def build():
    cfg = config.for_balance(1000)
    adapter = RobinhoodAgenticAdapter(FakeRH(), "581853207")
    journal = Journal(db.init_db(":memory:"))
    reg = build_full_registry(activation="paper")
    ctrl = Controller(cfg, reg, ConvictionGate(cfg), InsightEngine(cfg),
                      AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                      ExecutionHandler(adapter, cfg), journal, mode="rules",
                      execution_mode="execute", env_name="paper")
    ctrl.start_session(equity=1000.0)
    feed = FakeBarFeed({"SPY": daily(), "AMZN": intraday(), "WMT": intraday()})
    return ctrl, journal, feed


class TestOrchestrator(unittest.TestCase):
    def test_runs_cycle_and_reports(self):
        ctrl, journal, feed = build()
        orch = AutonomousOrchestrator(ctrl, journal, feed, ["AMZN", "WMT"],
                                      is_armed=lambda: True,
                                      now_fn=lambda: datetime(2026, 6, 16, 11, 0, tzinfo=ET))
        results = orch.run(max_cycles=2)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].session, "regular")
        report = orch.profit_report()
        self.assertIsNotNone(report.line())

    def test_not_armed_no_trade(self):
        ctrl, journal, feed = build()
        orch = AutonomousOrchestrator(ctrl, journal, feed, ["AMZN"],
                                      is_armed=lambda: False,
                                      now_fn=lambda: datetime(2026, 6, 16, 11, 0, tzinfo=ET))
        r = orch.run(max_cycles=1)[0]
        self.assertFalse(r.traded)
        self.assertEqual(r.reason, "not_armed")

    def test_closed_session_no_trade(self):
        ctrl, journal, feed = build()
        orch = AutonomousOrchestrator(ctrl, journal, feed, ["AMZN"],
                                      is_armed=lambda: True,
                                      now_fn=lambda: datetime(2026, 6, 13, 12, 0, tzinfo=ET))
        r = orch.run(max_cycles=1)[0]
        self.assertFalse(r.traded)
        self.assertIn("closed", r.reason)

    def test_profit_report_fields(self):
        ctrl, journal, feed = build()
        orch = AutonomousOrchestrator(ctrl, journal, feed, ["AMZN"],
                                      is_armed=lambda: True,
                                      now_fn=lambda: datetime(2026, 6, 16, 11, 0, tzinfo=ET))
        rep = orch.profit_report()
        self.assertEqual(rep.trades_closed, 0)
        self.assertEqual(rep.realized_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
