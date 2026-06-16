import tempfile
import unittest
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None

from src.ops.live_session import build_live_session
from src.ops.autonomous_loop import TradingLoop
from src.strategies.base import MarketState
from tests.test_prod_guardrails import FakeRH, et


class TestLiveSession(unittest.TestCase):
    def test_builds_with_recalibrated_config(self):
        sess = build_live_session(FakeRH(), "581853207",
                                  base_dir=tempfile.mkdtemp())
        # config recalibrated to the $1000 balance from get_portfolio
        self.assertEqual(sess.balance, 1000.0)
        self.assertEqual(sess.config["risk"]["catastrophic_halt_equity_usd"], 700.0)
        self.assertEqual(sess.config["risk"]["deployment_cap_usd"], 500.0)
        # SESSION_START audited
        self.assertGreaterEqual(sess.audit.count(), 1)

    def test_refuses_non_agentic_account(self):
        with self.assertRaises(Exception):
            build_live_session(FakeRH(agentic=False), "581853207",
                               base_dir=tempfile.mkdtemp())

    def test_refuses_margin_account(self):
        with self.assertRaises(Exception):
            build_live_session(FakeRH(acct_type="margin"), "581853207",
                               base_dir=tempfile.mkdtemp())


class FakeState:
    def __init__(self):
        self.halted = False
        self.halt_reason = ""
        self.trades_today = 0


class FakeController:
    def __init__(self):
        self.state = FakeState()
        self.ticks = 0

    def process_tick(self, states, now_et):
        self.ticks += 1
        self.state.trades_today += 1     # pretend a trade happened


def states_at(now_et="2026-06-16T11:00:00-04:00"):
    return {"AMZN": MarketState(ticker="AMZN", now_et=now_et, quote=249.0)}


class TestTradingLoop(unittest.TestCase):
    def _loop(self, ctrl, armed=True, session_dt=None, heartbeat=True, **kw):
        return TradingLoop(ctrl, is_armed=lambda: armed,
                           state_provider=lambda n: states_at(),
                           heartbeat=lambda: heartbeat,
                           now_fn=lambda: session_dt, audit=None, **kw)

    def test_trades_in_regular_session(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, session_dt=et(2026, 6, 16, 11, 0))  # Tue 11:00
        results = loop.run(max_cycles=1)
        self.assertTrue(results[0].traded)
        self.assertEqual(results[0].session, "regular")

    def test_not_armed_no_trade(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, armed=False, session_dt=et(2026, 6, 16, 11, 0))
        r = loop.run(max_cycles=1)[0]
        self.assertFalse(r.traded)
        self.assertEqual(r.reason, "not_armed")

    def test_closed_session_no_trade(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, session_dt=et(2026, 6, 13, 12, 0))  # Saturday
        r = loop.run(max_cycles=1)[0]
        self.assertFalse(r.traded)
        self.assertIn("closed", r.reason)

    def test_after_hours_blocked_unless_allowed(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, session_dt=et(2026, 6, 16, 17, 0))  # after-hours
        self.assertFalse(loop.run(max_cycles=1)[0].traded)
        # with extended allowed, it trades
        ctrl2 = FakeController()
        loop2 = self._loop(ctrl2, session_dt=et(2026, 6, 16, 17, 0), allow_extended=True)
        self.assertTrue(loop2.run(max_cycles=1)[0].traded)

    def test_halted_stops(self):
        ctrl = FakeController()
        ctrl.state.halted = True
        loop = self._loop(ctrl, session_dt=et(2026, 6, 16, 11, 0))
        r = loop.run(max_cycles=3)
        self.assertTrue(r[0].halted)
        self.assertEqual(len(r), 1)     # loop stops on halt

    def test_heartbeat_failure_halts(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, session_dt=et(2026, 6, 16, 11, 0), heartbeat=False)
        results = loop.run(max_cycles=5)
        self.assertTrue(any(x.halted for x in results))
        self.assertTrue(ctrl.state.halted)

    def test_bounded_by_max_cycles(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, session_dt=et(2026, 6, 16, 11, 0))
        self.assertEqual(len(loop.run(max_cycles=3)), 3)

    def test_stop_flag(self):
        ctrl = FakeController()
        loop = self._loop(ctrl, session_dt=et(2026, 6, 16, 11, 0))
        loop.stop = True
        self.assertEqual(len(loop.run(max_cycles=5)), 0)


if __name__ == "__main__":
    unittest.main()
