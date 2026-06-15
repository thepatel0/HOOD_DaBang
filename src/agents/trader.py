"""
HOOD DaBang — Trader + Portfolio Manager (Brief §5.2, Tier 3 Opus).

Trader: final synthesis per survivor after the debate -> a structured TradePlan
(or pass). Portfolio Manager: final authority before execution -> execute /
modify / reject, explicitly prohibited from trades motivated by "making the
daily number" or "making up an earlier loss".

Both degrade safely: if the LLM isn't spent or output is unparseable, the Trader
returns 'pass' and the PM returns 'reject' (fail-closed — never trade on a
missing/garbled decision).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import parse_json_lenient, clamp01


@dataclass
class TradePlan:
    decision: str                 # "trade" | "watch" | "pass"
    side: Optional[str] = None
    confidence: float = 0.0
    thesis_summary: str = ""
    invalidation: List[str] = field(default_factory=list)
    spent: bool = False


_TRADER_SYS = (
    "You are the Trader (final synthesis) on a disciplined desk that values trade "
    "QUALITY over quantity. Given the candidate, its thesis, and the bull/bear "
    "debate, decide. Return ONLY JSON: "
    '{"decision": "trade|watch|pass", "side": "long|short|null", "confidence": 0-1, '
    '"thesis_summary": "...", "invalidation": ["..."]}. Prefer PASS unless conviction '
    "is genuinely high. A mediocre trade is worse than no trade.")

_PM_SYS = (
    "You are the Portfolio Manager (final authority). Consider the TradePlan, the "
    "risk recommendation, and the portfolio context. Return ONLY JSON: "
    '{"decision": "execute|modify|reject", "reason": "...", "size_factor": 0-1}. '
    "NEVER approve a trade motivated by making the daily number or recovering an "
    "earlier loss. When in doubt, reject.")


def synthesize(llm, candidate_ctx: Dict, *, is_gate_survivor: bool = True) -> TradePlan:
    resp = llm.call("trader_synthesis", "trader", _TRADER_SYS,
                    [{"role": "user", "content": json.dumps(candidate_ctx, default=str)}],
                    is_gate_survivor=is_gate_survivor, max_tokens=600)
    if not resp.spent:
        return TradePlan(decision="pass", spent=False)
    d = parse_json_lenient(resp.text)
    if not d:
        return TradePlan(decision="pass", spent=True)
    return TradePlan(
        decision=d.get("decision", "pass"), side=d.get("side"),
        confidence=clamp01(d.get("confidence"), 0.0),
        thesis_summary=d.get("thesis_summary", ""),
        invalidation=list(d.get("invalidation", [])), spent=True)


@dataclass
class PMDecision:
    decision: str                 # "execute" | "modify" | "reject"
    reason: str = ""
    size_factor: float = 1.0
    spent: bool = False

    @property
    def approves(self) -> bool:
        return self.decision in ("execute", "modify")


def pm_decide(llm, plan_ctx: Dict, *, is_gate_survivor: bool = True) -> PMDecision:
    resp = llm.call("pm_decision", "portfolio_manager", _PM_SYS,
                    [{"role": "user", "content": json.dumps(plan_ctx, default=str)}],
                    is_gate_survivor=is_gate_survivor, max_tokens=400)
    if not resp.spent:
        return PMDecision(decision="reject", reason="llm_paused_fail_closed", spent=False)
    d = parse_json_lenient(resp.text)
    if not d:
        return PMDecision(decision="reject", reason="unparseable_fail_closed", spent=True)
    return PMDecision(
        decision=d.get("decision", "reject"), reason=d.get("reason", ""),
        size_factor=clamp01(d.get("size_factor"), 1.0), spent=True)
