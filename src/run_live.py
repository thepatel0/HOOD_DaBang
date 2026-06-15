"""
HOOD DaBang — main entry point (Brief §23).

  python -m src.run_live --paper --once --watchlist AAPL,MSFT,NVDA
  python -m src.run_live --live    # requires startup checks green + operator arming

Wires: config -> DB -> startup checks -> data feed -> Tier-0 analysts -> controller
-> dashboard. PAPER is the default and uses a fill simulator; LIVE builds the real
Robinhood MCP HTTP transport and refuses to start unless startup checks pass AND
the operator explicitly arms it. Going live with real capital is the operator's
switch — this program never auto-arms it.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

from . import config as cfgmod
from . import db
from .strategies.registry import StrategyRegistry, FIVE_GATES
from .strategies.intraday.orb import OpeningRangeBreakout
from .strategies.intraday.vwap_reversion import VWAPReversion
from .strategies.intraday.momentum import RelativeVolumeMomentum
from .analysts_local.technical import TechnicalAnalyst
from .conviction.gate import ConvictionGate
from .insight.engine import InsightEngine
from .decision.adaptive_risk import AdaptiveRiskGovernor
from .risk import RiskGate
from .mcp_client import RobinhoodMCPClient, MockTransport
from .execution import ExecutionHandler
from .journal import Journal
from .controller import Controller
from .data_feeds.bars import CachedBarFeed
from .strategies.base import MarketState, Bar
from .monitor.dashboard import snapshot_from_controller, render
from .ops.lifecycle import startup_checks


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMD", "SPY"]


def _sim_transport() -> MockTransport:
    return MockTransport({
        "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                  "filled_shares": p["shares"],
                                  "avg_fill_price": p["limit_price"]},
        "place_stop_order": lambda p: {"order_id": p["client_order_id"],
                                       "status": "accepted", "filled_shares": 0,
                                       "avg_fill_price": 0.0},
        "cancel_order": {}, "get_positions": {"positions": []},
    })


def build_system(cfg, mode: str):
    reg = StrategyRegistry(regime_allocations={
        "bull_trend_low_vol": {"orb": 0.15, "momentum": 0.12, "vwap_reversion": 0.05},
        "range_low_vol": {"vwap_reversion": 0.20, "orb": 0.05, "momentum": 0.05},
    })
    for strat in (OpeningRangeBreakout(), VWAPReversion(), RelativeVolumeMomentum()):
        reg.register(strat)
        # paper mode for the demo; live promotion requires all five gates
        reg.promote(strat.name, "paper")

    if mode == "live":
        from .mcp_http import HttpMCPTransport
        headers = {}
        token = os.environ.get("ROBINHOOD_MCP_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        transport = HttpMCPTransport(headers=headers)
    else:
        transport = _sim_transport()

    client = RobinhoodMCPClient(transport)
    journal = Journal(db.init_db(os.path.join(PROJECT_DIR, "data", "trader.db")))
    ctrl = Controller(cfg, reg, ConvictionGate(cfg), InsightEngine(cfg),
                      AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                      ExecutionHandler(client, cfg), journal, mode="rules")
    return ctrl, journal, client


def fetch_states(tickers: List[str], feed: CachedBarFeed,
                 regime: str = "bull_trend_low_vol") -> Dict[str, MarketState]:
    ta = TechnicalAnalyst()
    states: Dict[str, MarketState] = {}
    for t in tickers:
        res = feed.get_bars(t, interval="5m", lookback_days=5)
        if not res.bars or len(res.bars) < 30:
            res = feed.get_bars(t, interval="1d", lookback_days=60)
        if not res.bars or len(res.bars) < 30:
            continue
        bars = res.bars
        prior_close = bars[-2].c if len(bars) >= 2 else bars[-1].c
        ms = ta.compute(t, bars[-1].ts, bars[-1].c, {"1m": bars, "5m": bars},
                        prior_close=prior_close, regime=regime,
                        has_catalyst=False, adv_shares=5_000_000)
        states[t] = ms
    return states


def run_once(tickers: List[str], mode: str = "paper") -> None:
    cfg = cfgmod.load()
    ctrl, journal, client = build_system(cfg, mode)

    # startup gating
    from .reconciliation import Reconciler
    su = startup_checks(project_dir=PROJECT_DIR, cfg=cfg,
                        reconciler=Reconciler(client),
                        internal_positions=journal.open_positions())
    print("Startup:", su.selftest_summary)
    if not su.can_trade:
        print("REFUSING TO TRADE — blockers:")
        for b in su.blockers:
            print("  -", b)
        return

    ctrl.start_session(equity=1500.0)
    feed = CachedBarFeed(ttl_s=300)
    states = fetch_states(tickers, feed)
    if not states:
        print("No usable market data (feed degraded or empty).")
        return
    now = next(iter(states.values())).now_et
    ctrl.process_tick(states, now)

    snap = snapshot_from_controller(
        ctrl, regime="bull_trend_low_vol",
        gate_stats={"seen": len(states), "cleared": ctrl.state.trades_today},
        last_prices={t: ms.quote for t, ms in states.items()})
    snap.now_et = now
    print(render(snap))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="HOOD DaBang trading controller")
    p.add_argument("--paper", action="store_true", help="paper/sim mode (default)")
    p.add_argument("--live", action="store_true", help="LIVE — requires arming")
    p.add_argument("--once", action="store_true", help="run a single pipeline pass")
    p.add_argument("--watchlist", default=",".join(DEFAULT_WATCHLIST))
    p.add_argument("--arm-live", action="store_true",
                   help="explicit confirmation required to trade real capital")
    args = p.parse_args(argv)

    mode = "live" if args.live else "paper"
    if mode == "live" and not args.arm_live:
        print("LIVE mode requires --arm-live AND all 12 Definition-of-Done items "
              "green. Refusing. Run --paper to validate first.")
        return 2

    tickers = [t.strip().upper() for t in args.watchlist.split(",") if t.strip()]
    if args.once or mode == "paper":
        run_once(tickers, mode)
        return 0
    print("Continuous live loop is operator-armed only; not started.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
