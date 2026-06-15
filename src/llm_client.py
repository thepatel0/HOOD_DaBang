"""
HOOD DaBang — tier-aware LLM client (Brief §3.6, §26.7, failure modes #6/#24).

Every call is ROUTED through the Token Decision Engine (cache-first, cheapest
viable tier, gate-gated, budget-aware). The client:
  - validates the model used matches the agent's DECLARED tier (#24),
  - tracks cached vs fresh input tokens for the ~90% prompt-cache saving,
  - logs tokens + cost to the ledger via LLMBudget,
  - degrades gracefully (returns spent=False) instead of overspending.

Transport is pluggable: MockLLMTransport for tests/offline; AnthropicTransport
(guarded import) for live. The decision logic is identical either way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from .token_decision_engine import TokenDecisionEngine, Tier, BudgetState
from .llm_budget import LLMBudget


MODEL_TIER = {"haiku-4.5": Tier.HAIKU, "sonnet-4.6": Tier.SONNET, "opus-4.8": Tier.OPUS}


class TierMismatch(RuntimeError):
    """A call would use a model that doesn't match the agent's declared tier."""


@dataclass
class LLMResponse:
    text: str
    spent: bool                 # False => handled for $0 (degraded / cache / gate)
    model: Optional[str]
    reason: str
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class LLMTransport(Protocol):
    def complete(self, model: str, system: str, messages: List[Dict],
                 max_tokens: int, cached_tokens: int) -> Dict: ...


class LLMClient:
    def __init__(self, cfg: dict, budget: LLMBudget,
                 transport: LLMTransport, tde: Optional[TokenDecisionEngine] = None):
        self.cfg = cfg
        self.budget = budget
        self.transport = transport
        self.tde = tde or TokenDecisionEngine(cfg["llm"]["pricing"])
        self.agent_models: Dict[str, str] = cfg["llm"]["tiers"]

    def model_for_agent(self, agent: str) -> str:
        if agent not in self.agent_models:
            raise TierMismatch(f"agent {agent!r} has no declared tier/model")
        return self.agent_models[agent]

    def call(self, task: str, agent: str, system: str, messages: List[Dict], *,
             is_gate_survivor: bool = False, cache_hit: bool = False,
             cached_tokens: int = 0, max_tokens: int = 1024,
             est_in_tokens: int = 4000, est_out_tokens: int = 600,
             budget_pause_flag: bool = False) -> LLMResponse:
        # 1) route the work
        bstate: BudgetState = self.budget.state(budget_pause_flag)
        decision = self.tde.route(
            task, budget=bstate, is_gate_survivor=is_gate_survivor,
            cache_hit=cache_hit, est_in_tokens=est_in_tokens,
            est_out_tokens=est_out_tokens, est_cached_tokens=cached_tokens)

        if not decision.spend_tokens:
            return LLMResponse("", spent=False, model=None, reason=decision.reason)

        # 2) tier-integrity check (#24): the agent's declared model must match
        #    the tier the router chose for this task.
        declared = self.model_for_agent(agent)
        if MODEL_TIER.get(declared) != decision.tier:
            raise TierMismatch(
                f"agent {agent!r} declares {declared} (tier "
                f"{MODEL_TIER.get(declared)}) but task {task!r} routed to tier "
                f"{decision.tier}")

        # 3) execute
        out = self.transport.complete(declared, system, messages, max_tokens,
                                      cached_tokens)
        in_tok = int(out.get("input_tokens", est_in_tokens))
        cached = int(out.get("cached_tokens", cached_tokens))
        out_tok = int(out.get("output_tokens", est_out_tokens))
        latency = int(out.get("latency_ms", 0))

        # 4) log cost
        cost = self.budget.record(agent, declared, in_tok, out_tok, cached, latency)
        return LLMResponse(
            text=out.get("text", ""), spent=True, model=declared,
            reason="completed", input_tokens=in_tok, cached_tokens=cached,
            output_tokens=out_tok, cost_usd=cost)


# --------------------------------------------------------------------------- #
# Transports                                                                   #
# --------------------------------------------------------------------------- #
class MockLLMTransport:
    """Deterministic transport for tests/offline. Returns canned text + usage."""

    def __init__(self, text: str = "{}", input_tokens: int = 4000,
                 output_tokens: int = 600, cached_tokens: int = 0):
        self.text = text
        self.usage = dict(input_tokens=input_tokens, output_tokens=output_tokens,
                          cached_tokens=cached_tokens)
        self.calls: List[Dict] = []

    def complete(self, model, system, messages, max_tokens, cached_tokens):
        self.calls.append({"model": model, "system": system, "messages": messages,
                           "max_tokens": max_tokens, "cached_tokens": cached_tokens})
        return {"text": self.text, **self.usage, "cached_tokens": cached_tokens
                or self.usage["cached_tokens"], "latency_ms": 0}


class AnthropicTransport:
    """Live transport (Brief §3). Guarded import so the bedrock never needs the
    SDK. Uses prompt caching via cache_control on the system block. Tool names /
    model ids must match the deployed Anthropic API."""

    def __init__(self, api_key: Optional[str] = None):
        import os
        from anthropic import Anthropic  # guarded: only imported when used
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        # map our short ids to API model ids (Brief)
        self.model_ids = {
            "haiku-4.5": "claude-haiku-4-5-20251001",
            "sonnet-4.6": "claude-sonnet-4-6",
            "opus-4.8": "claude-opus-4-8",
        }

    def complete(self, model, system, messages, max_tokens, cached_tokens):
        import time
        t0 = time.time()
        sys_block = [{"type": "text", "text": system,
                      "cache_control": {"type": "ephemeral"}}]
        resp = self.client.messages.create(
            model=self.model_ids.get(model, model), max_tokens=max_tokens,
            system=sys_block, messages=messages)
        usage = resp.usage
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return {
            "text": text,
            "input_tokens": getattr(usage, "input_tokens", 0),
            "cached_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0),
            "latency_ms": int((time.time() - t0) * 1000),
        }
