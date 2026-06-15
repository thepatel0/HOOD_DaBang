"""
HOOD DaBang — agent base (Brief §4.6, §5.2).

Shared structured-output contract and JSON-parsing helper for the LLM agents.
Free-text reasoning lives inside `thesis`/`reasoning`, but every DECISION is
structured and schema-validated before any downstream consumer uses it — this
prevents the "the LLM said something vague and code interpreted it three ways"
failure mode.

All agents degrade safely: if the LLM call is not spent (budget/gate) or returns
unparseable output, the agent returns a conservative default (low confidence /
abstain) rather than guessing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentOutput:
    agent: str
    confidence: float = 0.0
    thesis: str = ""
    reasoning: str = ""
    proposal: Optional[Dict[str, Any]] = None
    risks: List[str] = field(default_factory=list)
    spent: bool = False              # whether an LLM call actually ran
    raw: str = ""


def parse_json_lenient(text: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON object from model text; tolerant of code fences and prose
    around the object. Returns None if no object can be extracted."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    # extract the first {...} block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
    return None


def clamp01(x: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (ValueError, TypeError):
        return default
