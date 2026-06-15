"""
HOOD DaBang — Bull/Bear debate (Brief §5.2, Tier 2 Sonnet).

Per Conviction-Gate survivor: Bull argues the long/short thesis with evidence;
Bear argues the strongest opposite case (and addresses Bull's points). Being
forced to write the strongest opposite case surfaces hidden assumptions
(TradingAgents finding: improves Sharpe, reduces drawdown).

Output: each side's confidence [0,1]; the debate margin (bull-bear) feeds the
Conviction Gate Stage-2 verdict. Degrades to neutral (0.5/0.5) when LLM is paused.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional

from .base import AgentOutput, parse_json_lenient, clamp01


@dataclass
class DebateResult:
    bull_confidence: float
    bear_confidence: float
    bull_thesis: str
    bear_thesis: str
    spent: bool

    @property
    def margin(self) -> float:
        return max(0.0, self.bull_confidence - self.bear_confidence)


_BULL_SYS = (
    "You are the Bull Researcher on a disciplined trading desk. Argue the case FOR "
    "this trade using the provided evidence. Cite specific factors. Return ONLY JSON: "
    '{"confidence": 0-1, "thesis": "...", "risks": ["..."]}. Do not sandbag — give '
    "your honest confidence that this trade works.")
_BEAR_SYS = (
    "You are the Bear Researcher. Argue the strongest case AGAINST this trade and "
    "address the Bull's points. Return ONLY JSON: "
    '{"confidence": 0-1, "thesis": "...", "risks": ["..."]}. confidence = how strongly '
    "you believe the trade FAILS.")


def _ctx(setup_ctx: Dict) -> str:
    return json.dumps(setup_ctx, default=str)


def run_debate(llm, setup_ctx: Dict, *, is_gate_survivor: bool = True) -> DebateResult:
    bull = llm.call("bull_debate", "bull", _BULL_SYS,
                    [{"role": "user", "content": _ctx(setup_ctx)}],
                    is_gate_survivor=is_gate_survivor, max_tokens=500)
    if not bull.spent:
        return DebateResult(0.5, 0.5, "", "", spent=False)
    bd = parse_json_lenient(bull.text) or {}
    bull_conf = clamp01(bd.get("confidence"), 0.5)

    bear_ctx = dict(setup_ctx)
    bear_ctx["bull_argument"] = bd.get("thesis", "")
    bear = llm.call("bear_debate", "bear", _BEAR_SYS,
                    [{"role": "user", "content": _ctx(bear_ctx)}],
                    is_gate_survivor=is_gate_survivor, max_tokens=500)
    br = parse_json_lenient(bear.text) or {}
    bear_conf = clamp01(br.get("confidence"), 0.5)

    return DebateResult(bull_conf, bear_conf, bd.get("thesis", ""),
                        br.get("thesis", ""), spent=True)
