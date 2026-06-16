"""
HOOD DaBang — Application: the integration glue (Brief §16, §22, §23).

Ties the pre-built components into one runnable system with the operator's hard
isolation guarantee:

  - ControlPlane  decides the execution mode (OFF/IDLE/RECOMMEND/PAPER/LIVE) and
                  gates live trading behind live_eligibility().
  - TWO RunEnvironments (production + paper) with entirely separate roots, asserted
                  isolated at startup — separate trader.db files, journals, memory.
  - TWO Controllers, each bound to its OWN Journal on its OWN db file (true data
                  isolation). Both share ONE KnowledgeBase — the single validated
                  paper->production bridge (conviction tilt only).
  - ResearchRunner  ingests real (or injected) data -> decisions per cycle.
  - PaperLearningLoop  mines the isolated paper journal for validated patterns.

A cycle routes by control.execution_mode():
  RECOMMEND -> production controller, recommend-only (writes recs, no orders)
  PAPER     -> paper controller, execute (isolated sandbox fills)
  LIVE      -> production controller, execute (only if control allows live)
  OFF/IDLE  -> no-op summary.

Feeds are injected so this runs offline in tests; defaults wire the real cached
bar feed in production.
"""
from __future__ import annotations

import os

from . import db
from .operator.control import ControlPlane
from .operator.environment import RunEnvironment
from .operator.eligibility import live_eligibility
from .strategies.all import build_full_registry
from .conviction.gate import ConvictionGate
from .insight.engine import InsightEngine
from .decision.adaptive_risk import AdaptiveRiskGovernor
from .risk import RiskGate
from .mcp_client import RobinhoodMCPClient, MockTransport
from .execution import ExecutionHandler
from .journal import Journal
from .controller import Controller
from .knowledge.base import KnowledgeBase
from .data_feeds.bars import CachedBarFeed
from .research.runner import ResearchRunner, ResearchSummary
from .research.paper_loop import PaperLearningLoop, LearningReport


def _sim_transport() -> MockTransport:
    """Fill simulator used for paper/recommend wiring (no network, $0)."""
    return MockTransport({
        "place_order": lambda p: {"order_id": p["client_order_id"], "status": "filled",
                                  "filled_shares": p["shares"],
                                  "avg_fill_price": p["limit_price"]},
        "place_stop_order": lambda p: {"order_id": p["client_order_id"],
                                       "status": "accepted", "filled_shares": 0,
                                       "avg_fill_price": 0.0},
        "cancel_order": {}, "get_positions": {"positions": []},
    })


def _expectancy_r(closed_trades) -> float:
    rs = [t["pnl_r"] for t in closed_trades if t.get("pnl_r") is not None]
    return sum(rs) / len(rs) if rs else 0.0


class Application:
    """The single runnable surface over the whole system. Owns the control plane,
    both isolated environments/controllers, the shared knowledge base, and the
    research/learning loops."""

    def __init__(self, cfg, base_data_dir, *, bar_feed=None, news_feed=None,
                 self_tests_green: bool = True, dod_overrides: bool = False):
        self.cfg = cfg
        self.base_data_dir = base_data_dir
        self.news_feed = news_feed
        self.bar_feed = bar_feed or CachedBarFeed()

        # ----- registry (all 19; intraday tradeable in sim) ---------------- #
        self.registry = build_full_registry(activation="paper")

        # ----- isolated environments (HARD requirement) -------------------- #
        self.prod_env = RunEnvironment.production(base_data_dir)
        self.paper_env = RunEnvironment.paper(base_data_dir)
        self.prod_env.assert_isolated_from(self.paper_env)
        self.prod_env.ensure_dirs()
        self.paper_env.ensure_dirs()

        # ----- shared knowledge base (the only paper->prod bridge) --------- #
        self.knowledge = KnowledgeBase(os.path.join(base_data_dir, "knowledge.db"))

        # ----- two journals on SEPARATE db files (true isolation) ---------- #
        self.prod_journal = Journal(db.init_db(self.prod_env.db_path))
        self.paper_journal = Journal(db.init_db(self.paper_env.db_path))

        # ----- two controllers, each bound to its own journal -------------- #
        self.prod_controller = self._build_controller(self.prod_journal, "production")
        self.paper_controller = self._build_controller(self.paper_journal, "paper")

        # ----- control plane: eligibility wired to the paper record -------- #
        self._self_tests_green = self_tests_green
        self._dod_overrides = dod_overrides
        self.control = ControlPlane(os.path.join(base_data_dir, "control.json"),
                                    eligibility_check=self._eligibility)

    # ----- construction helpers ----------------------------------------- #
    def _build_controller(self, journal: Journal, env_name: str) -> Controller:
        client = RobinhoodMCPClient(_sim_transport())
        ctrl = Controller(self.cfg, self.registry, ConvictionGate(self.cfg),
                          InsightEngine(self.cfg), AdaptiveRiskGovernor(self.cfg),
                          RiskGate(self.cfg), ExecutionHandler(client, self.cfg),
                          journal, mode="rules", env_name=env_name,
                          knowledge_base=self.knowledge)
        ctrl.start_session(equity=self.cfg["account"]["starting_capital_usd"])
        return ctrl

    def _eligibility(self):
        closed = self.paper_journal.closed_trades()
        return live_eligibility(
            self.registry, paper_trades=len(closed),
            paper_expectancy_r=_expectancy_r(closed),
            self_tests_green=self._self_tests_green,
            dod_overrides=self._dod_overrides)

    # ----- cycles -------------------------------------------------------- #
    def research_cycle(self, watchlist, now_et) -> ResearchSummary:
        """Route by control mode and run one ingestion->decision cycle."""
        mode = self.control.execution_mode()
        if mode == "RECOMMEND":
            ctrl, exec_mode = self.prod_controller, "recommend"
        elif mode == "PAPER":
            ctrl, exec_mode = self.paper_controller, "execute"
        elif mode == "LIVE":
            ctrl, exec_mode = self.prod_controller, "execute"
        else:  # OFF / IDLE -> do nothing
            return ResearchSummary(regime="n/a", names_screened=len(watchlist),
                                   states_built=0, recommendations=0,
                                   notes=f"mode {mode}: idle, no cycle run")
        ctrl.execution_mode = exec_mode
        runner = ResearchRunner(self.bar_feed, ctrl, news_feed=self.news_feed)
        return runner.run(watchlist, now_et)

    def paper_cycle(self, watchlist, now_et):
        """Run the isolated paper controller, then the self-improvement loop.
        Returns (ResearchSummary, LearningReport). Production data is untouched."""
        self.paper_controller.execution_mode = "execute"
        runner = ResearchRunner(self.bar_feed, self.paper_controller,
                                news_feed=self.news_feed)
        summary = runner.run(watchlist, now_et)
        report = PaperLearningLoop(self.paper_journal, self.knowledge).learn()
        return summary, report

    # ----- status ------------------------------------------------------- #
    def status(self) -> dict:
        s = self.control.state
        return {
            "mode": self.control.execution_mode(),
            "app": s.app, "research": s.research, "paper": s.paper,
            "trading": s.trading,
            "prod_trades": len(self.prod_journal.closed_trades()),
            "paper_trades": len(self.paper_journal.closed_trades()),
            "validated_knowledge": len(self.knowledge.validated_patterns()),
            "recommendations": len(self.prod_journal.recent_recommendations(1000)),
        }
