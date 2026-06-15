"""
HOOD DaBang — runnable demo of one synthetic trading day through the FULL
pipeline (no broker, no API, no tokens). Proves the machine works end to end:
screener -> Tier-0 -> strategies -> Conviction Gate -> thesis -> sizing ->
risk gate -> atomic execution -> journal.

Run:  PYTHONPATH=. .venv/bin/python scripts/demo_day.py
"""
from __future__ import annotations

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
from src.strategies.base import Bar


def synthetic_day():
    bars = []
    def ts(i): return f"2026-06-15T{9 + (30 + i)//60:02d}:{(30 + i)%60:02d}:00-04:00"
    for i in range(5):                          # opening range 100-101
        bars.append(Bar(ts(i), 100.4, 101.0, 100.0, 100.5, 2000))
    for i in range(5, 12):                       # quiet inside range
        bars.append(Bar(ts(i), 100.5, 100.9, 100.2, 100.6, 1500))
    bars.append(Bar(ts(12), 100.7, 101.6, 100.6, 101.5, 12000))  # breakout
    bars.append(Bar(ts(13), 101.5, 110.0, 101.4, 108.0, 15000))  # runs to target
    for i in range(14, 40):                      # back inside range
        bars.append(Bar(ts(i), 100.5, 100.8, 100.3, 100.5, 1200))
    return bars


def main():
    cfg = config.load()
    reg = StrategyRegistry(regime_allocations={"bull_trend_low_vol": {"orb": 0.15}})
    reg.register(OpeningRangeBreakout())
    for g in FIVE_GATES:
        reg.set_gate("orb", g, True)
    reg.promote("orb", "live")

    client = RobinhoodMCPClient(MockTransport({
        "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                  "filled_shares": p["shares"], "avg_fill_price": p["limit_price"]},
        "place_stop_order": lambda p: {"order_id": p["client_order_id"], "status": "accepted",
                                       "filled_shares": 0, "avg_fill_price": 0.0},
        "cancel_order": {},
    }))
    journal = Journal(db.init_db(":memory:"))
    ctrl = Controller(cfg, reg, ConvictionGate(cfg), InsightEngine(cfg),
                      AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                      ExecutionHandler(client, cfg), journal, mode="rules")
    ctrl.start_session(equity=1500.0)

    ta = TechnicalAnalyst()
    bars = synthetic_day()
    print("=" * 64)
    print("HOOD DaBang — synthetic trading day (rules mode, $0 tokens)")
    print("=" * 64)
    for i in range(10, len(bars)):
        cur = bars[i]
        ms = ta.compute("AAPL", cur.ts, cur.c, {"1m": bars[:i + 1]}, prior_close=100.0,
                        regime="bull_trend_low_vol", has_catalyst=True,
                        catalyst_age_min=5, catalyst_sources=2, adv_shares=5_000_000)
        ctrl.process_tick({"AAPL": ms}, cur.ts)

    print(f"\nStart equity:   $1,500.00")
    print(f"End equity:     ${ctrl.state.equity:,.2f}")
    print(f"Day P&L:        ${ctrl.state.day_pnl:+,.2f} "
          f"({ctrl.state.day_pnl/1500*100:+.2f}%)")
    print(f"Trades taken:   {ctrl.state.trades_today}")

    print("\n--- Conviction Gate decisions ---")
    for row in journal.conn.execute(
            "SELECT ticker, strategy, deterministic_score, advanced, reason "
            "FROM conviction_log").fetchall():
        flag = "ADVANCED" if row[3] else "dropped"
        print(f"  {row[0]} {row[1]} det={row[2]:.1f} [{flag}] {row[4]}")

    print("\n--- Trades ---")
    for t in journal.closed_trades():
        print(f"  {t['ticker']} {t['strategy']} -> {t['exit_reason']} "
              f"R={t['pnl_r']:+.2f} P&L=${t['pnl_dollars']:+.2f}")

    print("\n--- Thesis (the WHY, stored before entry) ---")
    for row in journal.conn.execute(
            "SELECT ticker, claim, mechanism, invalidation, confidence, base_rate "
            "FROM theses").fetchall():
        print(f"  {row[0]}: {row[1]}")
        print(f"    mechanism: {row[2][:80]}...")
        print(f"    invalidation: {row[3][:90]}")
        print(f"    confidence={row[4]} base_rate={row[5]}")
    print("=" * 64)


if __name__ == "__main__":
    main()
