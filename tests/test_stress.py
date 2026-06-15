"""Stress / resilience tests — the system must never crash or trade unsafely on
bad, missing, or adversarial inputs."""
import unittest

from src import config, db
from src.strategies.all import build_full_registry, all_strategies
from src.strategies.base import MarketState, Bar
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.execution import ExecutionHandler
from src.journal import Journal
from src.controller import Controller


def fill_transport():
    return MockTransport({
        "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                  "filled_shares": p["shares"], "avg_fill_price": p["limit_price"]},
        "place_stop_order": lambda p: {"order_id": p["client_order_id"],
                                       "status": "accepted", "filled_shares": 0, "avg_fill_price": 0.0},
        "cancel_order": {}, "get_positions": {"positions": []},
    })


def build_controller(mode="rules"):
    cfg = config.load()
    reg = build_full_registry(activation="paper")
    ctrl = Controller(cfg, reg, ConvictionGate(cfg), InsightEngine(cfg),
                      AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                      ExecutionHandler(RobinhoodMCPClient(fill_transport()), cfg),
                      Journal(db.init_db(":memory:")), mode=mode)
    ctrl.start_session(equity=1500.0)
    return ctrl


class TestResilience(unittest.TestCase):
    def test_empty_marketstate_no_crash(self):
        ctrl = build_controller()
        ms = MarketState(ticker="X", now_et="2026-06-15T11:00:00-04:00", quote=100.0)
        ctrl.process_tick({"X": ms}, ms.now_et)
        self.assertEqual(ctrl.state.trades_today, 0)

    def test_all_strategies_scan_garbage_no_crash(self):
        ms = MarketState(ticker="X", now_et="garbage", quote=float("nan"))
        for s in all_strategies():
            try:
                out = s.scan(ms)
                self.assertIsInstance(out, list)
            except Exception as e:
                self.fail(f"{s.name} crashed on garbage: {e}")

    def test_negative_and_zero_prices_no_trade(self):
        ctrl = build_controller()
        ms = MarketState(ticker="X", now_et="2026-06-15T11:00:00-04:00", quote=-5.0)
        ms.opening_range_high = 0
        ms.opening_range_low = 0
        ms.atr_1m = 0
        ctrl.process_tick({"X": ms}, ms.now_et)
        self.assertEqual(ctrl.state.trades_today, 0)

    def test_empty_tick_dict(self):
        ctrl = build_controller()
        ctrl.process_tick({}, "2026-06-15T11:00:00-04:00")
        self.assertEqual(ctrl.state.trades_today, 0)

    def test_loss_limit_halts(self):
        ctrl = build_controller()
        ctrl.state.day_pnl = -80.0
        ms = MarketState(ticker="X", now_et="2026-06-15T11:00:00-04:00", quote=100,
                         regime="bull_trend_low_vol")
        ctrl.process_tick({"X": ms}, ms.now_et)
        self.assertTrue(ctrl.state.halted)

    def test_drawdown_halts(self):
        ctrl = build_controller()
        ctrl.state.equity = 1100.0
        ctrl.state.ath = 1600.0       # -31% from ATH
        ms = MarketState(ticker="X", now_et="2026-06-15T11:00:00-04:00", quote=100,
                         regime="bull_trend_low_vol")
        ctrl.process_tick({"X": ms}, ms.now_et)
        self.assertTrue(ctrl.state.halted)

    def test_concurrency_cap_respected(self):
        from src.controller import OpenTrade
        from src.strategies.base import Position
        ctrl = build_controller()
        # fill to the days-1-30 cap of 3
        for t in ("A", "B", "C"):
            pos = Position(t, "long", 1, 100, 99, [(102, 1)], "orb", "t")
            ctrl.open[t] = OpenTrade(pos, 1, "th", 102, 1.0)
        self.assertTrue(ctrl._at_concurrency_cap())

    def test_extreme_volatility_data(self):
        ctrl = build_controller()
        bars = [Bar(f"2026-06-15T09:{30+i:02d}:00-04:00", 100, 1e6, 0.01, 100, 1e9)
                for i in range(40)]
        ms = MarketState(ticker="X", now_et="2026-06-15T09:50:00-04:00", quote=100,
                         regime="bull_trend_low_vol")
        ms.bars["1m"] = bars
        ms.atr_1m = 1e5
        # must not crash
        ctrl.process_tick({"X": ms}, ms.now_et)

    def test_many_names_one_tick(self):
        ctrl = build_controller()
        states = {}
        for i in range(50):
            t = f"T{i}"
            states[t] = MarketState(ticker=t, now_et="2026-06-15T11:00:00-04:00",
                                    quote=100.0, regime="range_low_vol")
        ctrl.process_tick(states, "2026-06-15T11:00:00-04:00")  # no crash, no bad trades

    def test_self_consistency_equity(self):
        # equity must equal start + sum of closed pnl after a run
        from tests.test_backtest import orb_win_bars
        from tests.test_integration import build_controller as bc, run_day
        ctrl, journal = bc()
        run_day(ctrl, orb_win_bars())
        closed = journal.closed_trades()
        total_pnl = sum(t["pnl_dollars"] for t in closed)
        self.assertAlmostEqual(ctrl.state.equity, 1500.0 + total_pnl, places=2)


if __name__ == "__main__":
    unittest.main()
