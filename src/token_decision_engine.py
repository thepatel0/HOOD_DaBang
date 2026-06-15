"""
HOOD DaBang — TOKEN DECISION ENGINE  ($0-first routing brain)

This component is the operator's explicit requirement: a decision engine that
determines, for any unit of work, whether it can be done for ZERO tokens in
deterministic local Python, or whether decision *quality* genuinely requires a
paid model — and, if so, the cheapest tier that meets the bar AND whether the
budget currently permits it.

It formalises Brief Sections 3.3-3.5 and 3.9 ("degrade, don't die") into a
single, testable policy object. Every routing decision is auditable.

Routing policy, in priority order:
  1. CACHE      — if a deterministic local cache can answer, spend nothing.
  2. TIER_FLOOR — route to the *minimum* tier whose quality clears the task bar.
  3. GATE       — paid tiers (1-3) are only reachable for Conviction-Gate
                  survivors (top 1-3). Everything else is forced to Tier 0.
  4. BUDGET     — if the daily/monthly budget is exhausted, force Tier 0 and
                  mark the work `degraded` (the system keeps trading on rules).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Optional


class Tier(IntEnum):
    LOCAL = 0   # deterministic Python / local ML inference — $0
    HAIKU = 1   # cheap classification / sentiment
    SONNET = 2  # multi-step reasoning, debate, synthesis
    OPUS = 3    # final synthesis, PM, meta-learning, judge


# Model id for each paid tier (mirrors config.llm.pricing keys).
TIER_MODEL: Dict[Tier, Optional[str]] = {
    Tier.LOCAL: None,
    Tier.HAIKU: "haiku-4.5",
    Tier.SONNET: "sonnet-4.6",
    Tier.OPUS: "opus-4.8",
}

# --------------------------------------------------------------------------- #
# CAPABILITY REGISTRY                                                          #
# The single source of truth for "what is the cheapest tier that can do X      #
# at acceptable quality." Derived from Brief 3.4. The KEY decision-quality      #
# principle: anything that is pure math, structured-data parsing, rules, or     #
# local ML inference is Tier 0 and must NEVER be sent to a model.               #
# --------------------------------------------------------------------------- #
MIN_TIER: Dict[str, Tier] = {
    # ---- Tier 0: deterministic, $0, runs daily as a reusable script -------- #
    "technical_analysis": Tier.LOCAL,
    "microstructure": Tier.LOCAL,
    "insider_form4_parse": Tier.LOCAL,
    "regime_classification": Tier.LOCAL,     # HMM + RandomForest local inference
    "screener": Tier.LOCAL,
    "conviction_stage1": Tier.LOCAL,
    "strategy_scan": Tier.LOCAL,
    "strategy_manage": Tier.LOCAL,
    "risk_gate": Tier.LOCAL,
    "killswitch_eval": Tier.LOCAL,
    "reconciliation": Tier.LOCAL,
    "position_sizing": Tier.LOCAL,
    "memory_retrieval": Tier.LOCAL,          # local sentence-transformers
    "backtest": Tier.LOCAL,
    "dashboard": Tier.LOCAL,
    "notifications": Tier.LOCAL,
    # ---- Tier 1: Haiku --------------------------------------------------- #
    "news_classification": Tier.HAIKU,
    "sentiment_scoring": Tier.HAIKU,
    # ---- Tier 2: Sonnet -------------------------------------------------- #
    "macro_synthesis": Tier.SONNET,
    "fundamentals_reading": Tier.SONNET,
    "insight_thesis": Tier.SONNET,
    "bull_debate": Tier.SONNET,
    "bear_debate": Tier.SONNET,
    "risk_debate": Tier.SONNET,
    "reflection": Tier.SONNET,
    "discovery": Tier.SONNET,
    # ---- Tier 3: Opus ---------------------------------------------------- #
    "trader_synthesis": Tier.OPUS,
    "pm_decision": Tier.OPUS,
    "meta_learning": Tier.OPUS,
    "llm_judge": Tier.OPUS,
}

# Tasks that may ONLY be spent on a Conviction-Gate survivor (top 1-3). This is
# the single biggest token saving in the brief (3.5).
GATED_TASKS = {
    "insight_thesis", "bull_debate", "bear_debate", "risk_debate",
    "trader_synthesis", "pm_decision",
}


@dataclass
class BudgetState:
    """Live spend snapshot, supplied by llm_budget. The decision engine never
    spends — it only routes — but it must *see* budget to fail closed."""
    daily_spent_usd: float = 0.0
    daily_budget_usd: float = 5.00
    monthly_spent_usd: float = 0.0
    monthly_budget_usd: float = 60.00
    budget_pause_flag: bool = False  # BUDGET_PAUSE.flag present on disk

    @property
    def daily_exhausted(self) -> bool:
        return self.budget_pause_flag or self.daily_spent_usd >= self.daily_budget_usd

    @property
    def monthly_exhausted(self) -> bool:
        return self.monthly_spent_usd >= self.monthly_budget_usd


@dataclass
class RoutingDecision:
    task: str
    tier: Tier
    model: Optional[str]
    spend_tokens: bool           # False == handled for $0
    reason: str
    degraded: bool = False       # True == we wanted a model but budget/gate forced Tier 0
    est_cost_usd: float = 0.0
    audit: Dict = field(default_factory=dict)


class TokenDecisionEngine:
    """Stateless-ish router. Construct once with pricing; call `route` per unit
    of work. Pure function of its inputs → fully testable, $0 to run."""

    def __init__(self, pricing: Optional[Dict[str, Dict[str, float]]] = None):
        # pricing: {model: {"input": $/Mtok, "output": $/Mtok}}
        self.pricing = pricing or {
            "haiku-4.5": {"input": 1.00, "output": 5.00},
            "sonnet-4.6": {"input": 3.00, "output": 15.00},
            "opus-4.8": {"input": 5.00, "output": 25.00},
        }

    # ----- cost estimation (used for pre-flight budget checks) ------------- #
    def estimate_cost(self, model: Optional[str], in_tokens: int,
                      out_tokens: int, cached_tokens: int = 0) -> float:
        if model is None:
            return 0.0
        p = self.pricing[model]
        # Cached input billed at ~10% (Brief 3.6: ~90% off cached input).
        fresh_in = max(0, in_tokens - cached_tokens)
        cost = (fresh_in * p["input"] + cached_tokens * p["input"] * 0.10
                + out_tokens * p["output"]) / 1_000_000.0
        return cost

    # ----- the decision ---------------------------------------------------- #
    def route(
        self,
        task: str,
        *,
        budget: BudgetState,
        is_gate_survivor: bool = False,
        cache_hit: bool = False,
        est_in_tokens: int = 0,
        est_out_tokens: int = 0,
        est_cached_tokens: int = 0,
    ) -> RoutingDecision:
        if task not in MIN_TIER:
            # Unknown task: fail closed to the most expensive review path is the
            # WRONG instinct for cost — fail closed to Tier 0 (do it locally or
            # not at all) and surface for a human to register the task.
            return RoutingDecision(
                task=task, tier=Tier.LOCAL, model=None, spend_tokens=False,
                reason="unknown_task_forced_local", degraded=True,
                audit={"hint": "register task in MIN_TIER"},
            )

        min_tier = MIN_TIER[task]

        # 1. Deterministic work is always free, full stop.
        if min_tier == Tier.LOCAL:
            return RoutingDecision(task, Tier.LOCAL, None, False,
                                   reason="tier0_deterministic")

        # 2. Cache short-circuit: a local cache answers for $0.
        if cache_hit:
            return RoutingDecision(task, Tier.LOCAL, None, False,
                                   reason="cache_hit_zero_cost",
                                   audit={"would_have_been": int(min_tier)})

        # 3. Gate-gating: paid reasoning only for top-1-3 survivors.
        if task in GATED_TASKS and not is_gate_survivor:
            return RoutingDecision(task, Tier.LOCAL, None, False,
                                   reason="not_gate_survivor_no_spend",
                                   degraded=False,
                                   audit={"would_have_been": int(min_tier)})

        # 4. Budget gating: degrade, don't die.
        if budget.daily_exhausted or budget.monthly_exhausted:
            which = "monthly" if budget.monthly_exhausted else "daily"
            return RoutingDecision(task, Tier.LOCAL, None, False,
                                   reason=f"{which}_budget_exhausted_degraded",
                                   degraded=True,
                                   audit={"would_have_been": int(min_tier)})

        # 5. Route to the minimum viable tier; pre-flight budget headroom check.
        model = TIER_MODEL[min_tier]
        est = self.estimate_cost(model, est_in_tokens, est_out_tokens, est_cached_tokens)
        if budget.daily_spent_usd + est > budget.daily_budget_usd:
            return RoutingDecision(task, Tier.LOCAL, None, False,
                                   reason="would_breach_daily_budget_degraded",
                                   degraded=True, est_cost_usd=est,
                                   audit={"would_have_been": int(min_tier)})

        return RoutingDecision(task, min_tier, model, True,
                               reason="route_to_min_tier", est_cost_usd=est,
                               audit={"gate_survivor": is_gate_survivor})
