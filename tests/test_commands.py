import unittest

from src import config, db
from src.journal import Journal
from src.operator.commands import CommandRouter
from src.strategies.all import build_full_registry


class FakeState:
    def __init__(self):
        self.equity = 1567.20
        self.session_start_equity = 1500.0
        self.day_pnl = 67.20
        self.ath = 1600.0
        self.trades_today = 1
        self.consecutive_losses = 0
        self.halted = False
        self.halt_reason = ""


class FakeGate:
    effective_execution_floor = 72


class FakeController:
    def __init__(self, cfg):
        self.cfg = cfg
        self.state = FakeState()
        self.gate = FakeGate()
        self.open = {}

    def _flatten_all(self, states, now, reason):
        self.open.clear()


class TestCommands(unittest.TestCase):
    def setUp(self):
        cfg = config.load()
        self.ctrl = FakeController(cfg)
        self.journal = Journal(db.init_db(":memory:"))
        self.reg = build_full_registry()
        self.router = CommandRouter(self.ctrl, self.journal, None, self.reg)

    def test_status(self):
        out = self.router.dispatch("/status")
        self.assertIn("equity", out)
        self.assertIn("ARMED", out)

    def test_unknown_command(self):
        self.assertIn("unknown command", self.router.dispatch("/florble"))

    def test_help(self):
        self.assertIn("/conviction", self.router.dispatch("/help"))

    def test_halt_and_resume(self):
        self.router.dispatch("/halt")
        self.assertTrue(self.ctrl.state.halted)
        self.router.dispatch("/resume")
        self.assertFalse(self.ctrl.state.halted)

    def test_conviction_from_log(self):
        self.journal.log_conviction("t", "AMD", "orb", 69.0, None, False, False,
                                    "below_floor")
        out = self.router.dispatch("/conviction")
        self.assertIn("AMD", out)

    def test_why_no_trade_when_zero(self):
        self.ctrl.state.trades_today = 0
        out = self.router.dispatch("/why-no-trade")
        self.assertIn("healthy", out)

    def test_why_trade(self):
        tid = self.journal.record_trade(
            ticker="AAPL", strategy="orb", strategy_version="1.0.0", side="long",
            entry_ts="t", entry_price=101, entry_shares=4, stop_price=99,
            conviction_score=80, thesis_id="th1", market_regime="bull_trend_low_vol",
            order_id="O1")
        out = self.router.dispatch(f"/why {tid}")
        self.assertIn("AAPL", out)

    def test_strategy_toggle(self):
        out = self.router.dispatch("/strategy orb off")
        self.assertIn("paused", out)
        self.assertEqual(self.reg.get("orb").strategy.activation_status, "paused")

    def test_strategy_unknown(self):
        self.assertIn("no strategy", self.router.dispatch("/strategy florble on"))

    def test_rejected(self):
        self.journal.log_conviction("t", "X", "orb", 50.0, None, False, False, "low")
        self.assertIn("X", self.router.dispatch("/rejected"))


if __name__ == "__main__":
    unittest.main()
