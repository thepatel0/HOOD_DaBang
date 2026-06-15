import unittest

from src import config, db
from src.strategies.registry import StrategyRegistry, FIVE_GATES
from src.strategies.intraday.orb import OpeningRangeBreakout
from src.analysts_local.technical import TechnicalAnalyst
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.execution import ExecutionHandler
from src.journal import Journal
from src.controller import Controller
from tests.test_backtest import orb_win_bars


def fill_transport(stop_status="accepted"):
    responses = {
        "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                  "filled_shares": p["shares"],
                                  "avg_fill_price": p["limit_price"]},
        "place_stop_order": lambda p: {"order_id": p["client_order_id"],
                                       "status": stop_status, "filled_shares": 0,
                                       "avg_fill_price": 0.0},
        "cancel_order": {},
    }
    return MockTransport(responses)


def build_controller(stop_status="accepted"):
    cfg = config.load()
    reg = StrategyRegistry(regime_allocations={"bull_trend_low_vol": {"orb": 0.15}})
    orb = OpeningRangeBreakout()
    reg.register(orb)
    for g in FIVE_GATES:           # promote to live so it's tradeable
        reg.set_gate("orb", g, True)
    reg.promote("orb", "live")
    gate = ConvictionGate(cfg)
    insight = InsightEngine(cfg)
    governor = AdaptiveRiskGovernor(cfg)
    risk_gate = RiskGate(cfg)
    client = RobinhoodMCPClient(fill_transport(stop_status))
    execution = ExecutionHandler(client, cfg)
    journal = Journal(db.init_db(":memory:"))
    ctrl = Controller(cfg, reg, gate, insight, governor, risk_gate, execution,
                      journal, mode="rules")
    ctrl.start_session(equity=1500.0)
    return ctrl, journal


def run_day(ctrl, bars, ticker="AAPL", warmup=10):
    ta = TechnicalAnalyst()
    for i in range(warmup, len(bars)):
        window = bars[:i + 1]
        cur = bars[i]
        ms = ta.compute(ticker, cur.ts, cur.c, {"1m": window}, prior_close=100.0,
                        regime="bull_trend_low_vol", has_catalyst=True,
                        catalyst_age_min=5, catalyst_sources=2, adv_shares=5_000_000)
        ctrl.process_tick({ticker: ms}, cur.ts)


class TestIntegrationPipeline(unittest.TestCase):
    def test_full_day_produces_thesis_backed_trade(self):
        ctrl, journal = build_controller()
        run_day(ctrl, orb_win_bars())
        # a trade was recorded, with a thesis and a stop
        closed = journal.closed_trades()
        self.assertGreaterEqual(len(closed), 1)
        # every trade references a stored thesis (no thesis-less trades)
        trade_rows = ctrl.journal.conn.execute(
            "SELECT thesis_id, order_id, conviction_score FROM trades").fetchall()
        for thesis_id, order_id, conviction in trade_rows:
            self.assertTrue(thesis_id)
            self.assertIsNotNone(journal.get_thesis(thesis_id))
            self.assertGreaterEqual(conviction, ctrl.cfg["conviction"]["execution_floor"])

    def test_winning_trade_updates_equity(self):
        ctrl, journal = build_controller()
        run_day(ctrl, orb_win_bars())
        self.assertGreater(ctrl.state.equity, 1500.0)     # profitable day
        self.assertGreater(ctrl.state.day_pnl, 0)
        closed = journal.closed_trades()
        self.assertEqual(closed[0]["exit_reason"], "target")
        self.assertGreater(closed[0]["pnl_r"], 0)

    def test_conviction_log_populated(self):
        ctrl, journal = build_controller()
        run_day(ctrl, orb_win_bars())
        n = ctrl.journal.conn.execute("SELECT COUNT(*) FROM conviction_log").fetchone()[0]
        self.assertGreater(n, 0)

    def test_equity_curve_written(self):
        ctrl, journal = build_controller()
        run_day(ctrl, orb_win_bars())
        n = ctrl.journal.conn.execute("SELECT COUNT(*) FROM equity_curve").fetchone()[0]
        self.assertGreater(n, 0)


class FullModeTransport:
    """Scripted LLM for the full §4.4 pipeline (insight + debate + trader + PM)."""
    def __init__(self, bull=0.85, bear=0.30, trader="trade", pm="execute"):
        self.bull, self.bear, self.trader, self.pm = bull, bear, trader, pm

    def complete(self, model, system, messages, max_tokens, cached_tokens):
        import json
        if system.startswith("You are the Insight"):
            t = json.dumps({"claim": "AAPL long to target", "mechanism": "breakout "
                            "continuation on volume", "invalidation": ["loses VWAP"],
                            "expected_path": "up", "confidence": 0.8})
        elif system.startswith("You are the Bull"):
            t = json.dumps({"confidence": self.bull, "thesis": "bull", "risks": []})
        elif system.startswith("You are the Bear"):
            t = json.dumps({"confidence": self.bear, "thesis": "bear", "risks": []})
        elif system.startswith("You are the Trader"):
            t = json.dumps({"decision": self.trader, "side": "long",
                            "confidence": 0.78, "thesis_summary": "go",
                            "invalidation": ["loses vwap"]})
        else:
            t = json.dumps({"decision": self.pm, "reason": "ok", "size_factor": 1.0})
        return {"text": t, "input_tokens": 3000, "output_tokens": 300,
                "cached_tokens": cached_tokens, "latency_ms": 0}


def build_full_controller(transport):
    from src.llm_budget import LLMBudget
    from src.llm_client import LLMClient
    from datetime import datetime, timezone
    cfg = config.load()
    reg = StrategyRegistry(regime_allocations={"bull_trend_low_vol": {"orb": 0.15}})
    reg.register(OpeningRangeBreakout())
    for g in FIVE_GATES:
        reg.set_gate("orb", g, True)
    reg.promote("orb", "live")
    client = RobinhoodMCPClient(fill_transport())
    journal = Journal(db.init_db(":memory:"))
    budget = LLMBudget(db.init_ledger(":memory:"), cfg,
                       now=lambda: datetime(2026, 6, 15, tzinfo=timezone.utc))
    llm = LLMClient(cfg, budget, transport)
    ctrl = Controller(cfg, reg, ConvictionGate(cfg), InsightEngine(cfg, llm_client=llm),
                      AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                      ExecutionHandler(client, cfg), journal, mode="full",
                      llm_client=llm)
    ctrl.start_session(equity=1500.0)
    return ctrl, journal


class TestFullModePipeline(unittest.TestCase):
    def test_full_llm_pipeline_executes_trade(self):
        ctrl, journal = build_full_controller(FullModeTransport(bull=0.85, bear=0.30))
        run_day(ctrl, orb_win_bars())
        self.assertGreaterEqual(len(journal.closed_trades()), 1)

    def test_pm_reject_blocks_trade(self):
        ctrl, journal = build_full_controller(FullModeTransport(pm="reject"))
        run_day(ctrl, orb_win_bars())
        self.assertEqual(ctrl.state.trades_today, 0)

    def test_trader_pass_blocks_trade(self):
        ctrl, journal = build_full_controller(FullModeTransport(trader="pass"))
        run_day(ctrl, orb_win_bars())
        self.assertEqual(ctrl.state.trades_today, 0)


class TestChaos(unittest.TestCase):
    def test_daily_loss_limit_halts_and_flattens(self):
        ctrl, journal = build_controller()
        ctrl.start_session(equity=1500.0)
        # force a loss beyond the -5% limit
        ctrl.state.day_pnl = -80.0    # -5% of 1500 = -75
        from src.strategies.base import MarketState
        ms = MarketState(ticker="AAPL", now_et="2026-06-15T10:00:00-04:00", quote=100)
        ms.regime = "bull_trend_low_vol"
        ctrl.process_tick({"AAPL": ms}, ms.now_et)
        self.assertTrue(ctrl.state.halted)
        self.assertIn("daily_loss_limit", ctrl.state.halt_reason)

    def test_stop_rejection_prevents_unhedged_position(self):
        # broker rejects the protective stop -> execution flattens -> NO open trade
        ctrl, journal = build_controller(stop_status="rejected")
        run_day(ctrl, orb_win_bars())
        self.assertEqual(len(ctrl.open), 0)              # no unhedged position held
        # no completed trade was journaled as held/closed via this path
        open_pos = ctrl.journal.open_positions()
        self.assertEqual(open_pos, {})

    def test_halted_takes_no_new_entries(self):
        ctrl, journal = build_controller()
        ctrl.start_session(equity=1500.0)
        ctrl.state.halted = True
        before = ctrl.state.trades_today
        run_day(ctrl, orb_win_bars())
        self.assertEqual(ctrl.state.trades_today, before)  # no entries while halted


if __name__ == "__main__":
    unittest.main()
