"""
HOOD DaBang — autonomous orchestrator runner.

  # PAPER (free, safe, real market data): proves the full loop works
  PYTHONPATH=. .venv/bin/python scripts/run_autonomous.py --paper --cycles 3 --interval 60

  # LIVE (real orders) — requires the app's OWN Robinhood connection + arming:
  ROBINHOOD_MCP_URL=... ROBINHOOD_MCP_TOKEN=... \
  PYTHONPATH=. .venv/bin/python scripts/run_autonomous.py --live --cycles N --interval 60

The loop: wake -> research real data -> decision tree (conviction + risk +
deployment cap) -> place buy/sell via the wired adapter -> manage stops/targets ->
count P&L. PAPER fills are simulated; LIVE places real orders ONLY when the app
has its own broker connection AND the control plane is armed. The chat connector
cannot drive this process — see --live notes.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, List

from src import config as cfgmod, db
from src.robinhood import RobinhoodAgenticAdapter
from src.mcp_client import MCPTransport
from src.execution import ExecutionHandler
from src.journal import Journal
from src.controller import Controller
from src.conviction.gate import ConvictionGate
from src.insight.engine import InsightEngine
from src.decision.adaptive_risk import AdaptiveRiskGovernor
from src.risk import RiskGate
from src.strategies.all import build_full_registry
from src.knowledge.base import KnowledgeBase
from src.data_feeds.bars import CachedBarFeed
from src.ops.orchestrator import AutonomousOrchestrator

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNT = "581853207"
DEFAULT_WATCHLIST = ["AMZN", "GOOGL", "WMT", "SOFI", "NVDA", "AAPL", "MSFT"]


class SimRobinhoodTransport:
    """Paper transport: speaks the REAL tool names but simulates fills at the
    limit price. Lets the orchestrator run the whole loop for $0 with no broker."""
    def list_tools(self):
        from src.robinhood import REAL_TOOLS
        return list(REAL_TOOLS)

    def call(self, tool, params):
        if tool == "get_accounts":
            return {"data": {"accounts": [{"account_number": ACCOUNT,
                    "agentic_allowed": True, "type": "cash"}]}}
        if tool == "get_portfolio":
            return {"data": {"total_value": "1000", "cash": "1000",
                    "equity_value": "0", "buying_power": {"buying_power": "1000.0"}}}
        if tool == "get_equity_positions":
            return {"data": {"positions": []}}
        if tool == "review_equity_order":
            return {"data": {"order_checks": {}}}
        if tool == "place_equity_order":
            return {"data": {"id": params.get("ref_id", "sim"), "state": "filled",
                    "cumulative_quantity": params.get("quantity", "1"),
                    "average_price": params.get("limit_price",
                                                params.get("stop_price", "0"))}}
        return {"data": {}}


def build_transport(live: bool) -> MCPTransport:
    if not live:
        return SimRobinhoodTransport()
    url = os.environ.get("ROBINHOOD_MCP_URL")
    token = os.environ.get("ROBINHOOD_MCP_TOKEN")
    if not url or not token:
        print("LIVE requires ROBINHOOD_MCP_URL and ROBINHOOD_MCP_TOKEN env vars "
              "(the app's OWN broker connection). The chat connector cannot drive "
              "this standalone process. Refusing live without them.")
        sys.exit(2)
    from src.mcp_http import HttpMCPTransport
    return HttpMCPTransport(url=url, headers={"Authorization": f"Bearer {token}"})


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--paper", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--watchlist", default=",".join(DEFAULT_WATCHLIST))
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--interval", type=float, default=60.0)
    p.add_argument("--balance", type=float, default=1000.0)
    args = p.parse_args(argv)
    live = args.live and not args.paper
    watchlist = [t.strip().upper() for t in args.watchlist.split(",") if t.strip()]

    transport = build_transport(live)
    adapter = RobinhoodAgenticAdapter(transport, ACCOUNT)
    adapter.assert_agentic_account()
    bal = adapter.get_account().buying_power if live else args.balance
    cfg = cfgmod.for_balance(bal)

    env = "prod" if live else "paper"
    base = os.path.join(PROJECT_DIR, "data", env)
    os.makedirs(base, exist_ok=True)
    journal = Journal(db.init_db(os.path.join(base, "trader.db")))
    knowledge = KnowledgeBase(os.path.join(PROJECT_DIR, "data", "knowledge.db"))
    registry = build_full_registry(activation="paper")
    controller = Controller(cfg, registry, ConvictionGate(cfg), InsightEngine(cfg),
                            AdaptiveRiskGovernor(cfg), RiskGate(cfg),
                            ExecutionHandler(adapter, cfg), journal, mode="rules",
                            execution_mode="execute", env_name=env,
                            knowledge_base=knowledge)
    controller.start_session(equity=bal)

    # the operator's arm switch (LIVE requires an explicit env opt-in)
    armed = (not live) or os.environ.get("HOODDABANG_ARM_LIVE") == "yes"
    orch = AutonomousOrchestrator(controller, journal, CachedBarFeed(ttl_s=120),
                                  watchlist, is_armed=lambda: armed,
                                  heartbeat=lambda: True)

    print(f"=== HOOD DaBang autonomous orchestrator [{'LIVE' if live else 'PAPER'}] ===")
    print(f"account {ACCOUNT} · balance ${bal:,.2f} · deploy cap "
          f"${cfg['risk']['deployment_cap_usd']:.0f} · armed={armed}")
    results = orch.run(max_cycles=args.cycles, sleep_s=args.interval)
    for r in results:
        print(f"  cycle {r.cycle}: session={r.session} traded={r.traded} "
              f"reason={r.reason} trades_today={r.trades_today}")
    print(orch.profit_report().line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
