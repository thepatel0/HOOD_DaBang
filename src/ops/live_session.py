"""
HOOD DaBang — live session builder (NEXT_STEPS Priorities 1, 2, 5).

Assembles a PRODUCTION-ready trading session against the real Robinhood Agentic
account: real adapter, balance-recalibrated config, immutable audit log, the
agentic+cash (margin-off) guard, and the execution handler — all wired so the
controller places real orders through review_equity_order -> place_equity_order
within the deployment cap. The OPERATOR arms and runs this; it never self-arms.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .. import config as cfgmod
from .. import db
from ..audit import AuditLog
from ..robinhood import RobinhoodAgenticAdapter
from ..execution import ExecutionHandler
from ..journal import Journal
from ..controller import Controller
from ..conviction.gate import ConvictionGate
from ..insight.engine import InsightEngine
from ..decision.adaptive_risk import AdaptiveRiskGovernor
from ..risk import RiskGate
from ..strategies.all import build_full_registry
from ..knowledge.base import KnowledgeBase


@dataclass
class LiveSession:
    config: dict
    adapter: RobinhoodAgenticAdapter
    controller: Controller
    journal: Journal
    audit: AuditLog
    account_number: str
    balance: float


def build_live_session(transport, account_number: str, *, base_dir: str,
                       balance: Optional[float] = None,
                       autonomous: bool = False) -> LiveSession:
    """Build the production session. Performs the session-start safety checks
    (NEXT_STEPS P2): agentic_allowed + cash (margin-off) guard, authoritative
    buying power. Raises before any trading if a precondition fails."""
    prod_dir = os.path.join(base_dir, "prod")
    os.makedirs(prod_dir, exist_ok=True)
    audit = AuditLog(os.path.join(prod_dir, "audit.db"))

    adapter = RobinhoodAgenticAdapter(transport, account_number, audit=audit)
    # §34 tool-surface check + margin/cash guard BEFORE anything else
    missing = adapter.validate_tool_map()
    if missing:
        raise RuntimeError(f"MCP tool surface mismatch (refuse to trade): {missing}")
    adapter.assert_agentic_account()

    acct = adapter.get_account()                 # authoritative buying power
    if balance is None:
        balance = acct.buying_power
    cfg = cfgmod.for_balance(balance)            # recalibrate caps to real balance

    journal = Journal(db.init_db(os.path.join(prod_dir, "trader.db")))
    knowledge = KnowledgeBase(os.path.join(base_dir, "knowledge.db"))
    registry = build_full_registry(activation="paper")  # nothing live until gates pass

    controller = Controller(
        cfg, registry, ConvictionGate(cfg), InsightEngine(cfg),
        AdaptiveRiskGovernor(cfg), RiskGate(cfg),
        ExecutionHandler(adapter, cfg), journal, mode="rules",
        execution_mode="execute", env_name="production", knowledge_base=knowledge)
    controller.start_session(equity=balance)

    audit.record("SESSION_START", account_number=account_number,
                 outcome={"balance": balance, "buying_power": acct.buying_power,
                          "deployment_cap": cfg["risk"]["deployment_cap_usd"],
                          "autonomous": autonomous})
    return LiveSession(config=cfg, adapter=adapter, controller=controller,
                       journal=journal, audit=audit, account_number=account_number,
                       balance=balance)
