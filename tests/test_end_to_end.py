"""
End-to-end operational test — the full daily rhythm as one system:
screener -> research pipeline -> controller -> journal -> reflector -> weekly review.
"""
import unittest

from src import config, db
from src.screener.screener import Screener, Candidate
from src.research.pipeline import ResearchPipeline, TickerContext
from src.strategies.all import build_full_registry
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.mcp_client import RobinhoodMCPClient, MockTransport
from src.execution import ExecutionHandler
from src.journal import Journal
from src.controller import Controller
from src.agents.reflector import Reflector
from src.learning import WeeklyReview
from src.strategies.base import Bar


def fill_transport():
    return MockTransport({
        "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                  "filled_shares": p["shares"], "avg_fill_price": p["limit_price"]},
        "place_stop_order": lambda p: {"order_id": p["client_order_id"],
                                       "status": "accepted", "filled_shares": 0, "avg_fill_price": 0.0},
        "cancel_order": {}, "get_positions": {"positions": []},
    })


def orb_day_bars(seed_price=100.0, win=True):
    """A day with a clean ORB breakout that wins (or fails)."""
    bars = []
    def ts(i): return f"2026-06-15T{9 + (30 + i)//60:02d}:{(30 + i)%60:02d}:00-04:00"
    for i in range(5):
        bars.append(Bar(ts(i), seed_price+0.4, seed_price+1.0, seed_price, seed_price+0.5, 2000))
    for i in range(5, 12):
        bars.append(Bar(ts(i), seed_price+0.5, seed_price+0.9, seed_price+0.2, seed_price+0.6, 1500))
    bars.append(Bar(ts(12), seed_price+0.7, seed_price+1.6, seed_price+0.6, seed_price+1.5, 12000))
    if win:
        bars.append(Bar(ts(13), seed_price+1.5, seed_price+10, seed_price+1.4, seed_price+8, 15000))
    else:
        bars.append(Bar(ts(13), seed_price+1.5, seed_price+1.6, seed_price-3, seed_price-2.5, 15000))
    for i in range(14, 40):
        bars.append(Bar(ts(i), seed_price+0.5, seed_price+0.8, seed_price+0.3, seed_price+0.5, 1200))
    return bars


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.cfg = config.load()
        self.journal = Journal(db.init_db(":memory:"))
        self.reg = build_full_registry(activation="paper")
        self.ctrl = Controller(
            self.cfg, self.reg, ConvictionGate(self.cfg), InsightEngine(self.cfg),
            AdaptiveRiskGovernor(self.cfg), RiskGate(self.cfg),
            ExecutionHandler(RobinhoodMCPClient(fill_transport()), self.cfg),
            self.journal, mode="rules")
        self.ctrl.start_session(equity=1500.0)
        self.pipeline = ResearchPipeline()
        self.screener = Screener(self.cfg)

    def test_screener_to_watchlist(self):
        cands = [Candidate("AAPL", 190, 50_000_000, 0.02, gap_pct=0.0, rvol=3.0),
                 Candidate("PENNY", 2, 10_000_000, 0.05, rvol=5.0),
                 Candidate("THIN", 50, 100_000, 0.03, rvol=4.0)]
        wl = self.screener.combined_watchlist(cands)
        self.assertEqual(wl, ["AAPL"])   # only the liquid name survives

    def test_full_day_via_pipeline(self):
        bars = orb_day_bars(win=True)
        ctx = TickerContext(prior_close=100.0, adv_shares=50_000_000,
                            has_catalyst=True, catalyst_age_min=5, catalyst_sources=2)
        for i in range(10, len(bars)):
            ms = self.pipeline.build("AAPL", bars[i].ts, bars[i].c, {"1m": bars[:i+1]},
                                     "bull_trend_low_vol", ctx=ctx)
            self.ctrl.process_tick({"AAPL": ms}, bars[i].ts)
        # a thesis-backed trade happened and was journaled
        self.assertGreaterEqual(len(self.journal.closed_trades()), 1)
        self.assertGreater(self.ctrl.state.equity, 1500.0)

    def test_multi_day_then_reflection_and_weekly(self):
        # simulate 3 days (2 wins, 1 loss), reflect each, then weekly review
        for day, win in enumerate([True, False, True]):
            self.ctrl.start_session(equity=self.ctrl.state.equity if day else 1500.0)
            bars = orb_day_bars(seed_price=100.0 + day, win=win)
            ctx = TickerContext(prior_close=100.0 + day, adv_shares=50_000_000,
                                has_catalyst=True, catalyst_age_min=5, catalyst_sources=2)
            for i in range(10, len(bars)):
                ms = self.pipeline.build("AAPL", bars[i].ts, bars[i].c,
                                         {"1m": bars[:i+1]}, "bull_trend_low_vol", ctx=ctx)
                self.ctrl.process_tick({"AAPL": ms}, bars[i].ts)

        closed = self.journal.closed_trades()
        self.assertGreaterEqual(len(closed), 3)

        # reflect each closed trade
        reflector = Reflector()
        for t in closed:
            ref = reflector.reflect_trade(
                trade_id=t["id"], ticker=t["ticker"], side="long", pnl_r=t["pnl_r"],
                exit_reason=t["exit_reason"], base_rate=0.5)
            self.assertIn(ref.good_or_bad_loss, ("good", "bad", "n/a"))

        # weekly review runs over the journal
        report = WeeklyReview(self.cfg, journal=self.journal).run()
        self.assertGreaterEqual(report.session.n_trades, 3)
        self.assertGreaterEqual(report.proposed_floor, self.cfg["conviction"]["floor_min"])
        self.assertLessEqual(report.proposed_floor, self.cfg["conviction"]["floor_max"])

    def test_losing_day_then_halt_protection(self):
        # a big loss should not push equity below the catastrophic floor unnoticed
        bars = orb_day_bars(win=False)
        ctx = TickerContext(prior_close=100.0, adv_shares=50_000_000,
                            has_catalyst=True, catalyst_age_min=5, catalyst_sources=2)
        for i in range(10, len(bars)):
            ms = self.pipeline.build("AAPL", bars[i].ts, bars[i].c, {"1m": bars[:i+1]},
                                     "bull_trend_low_vol", ctx=ctx)
            self.ctrl.process_tick({"AAPL": ms}, bars[i].ts)
        # equity stays well above the catastrophic floor (1.5% risk cap protects it)
        self.assertGreater(self.ctrl.state.equity,
                           self.cfg["risk"]["catastrophic_halt_equity_usd"])


if __name__ == "__main__":
    unittest.main()
