"""
HOOD DaBang — deterministic news classifier (Tier 0, $0).

Keyword-based classification of real RSS headlines into catalyst categories with
direction and severity — so the research engine detects catalysts from live news
WITHOUT spending tokens. The Haiku NewsAnalyst remains available as a quality
upgrade for ambiguous batches; this is the always-on, free baseline.

Prompt-injection is irrelevant here (no LLM): headlines are pure data matched
against fixed keyword rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# (category, severity, direction, keyword patterns)
_RULES: List[Tuple[str, int, str, List[str]]] = [
    ("M&A", 3, "bull", ["acquire", "acquisition", "merger", "to buy", "takeover",
                        "buyout", "deal to"]),
    ("fda", 3, "bull", ["fda approval", "approved by the fda", "phase 3 success",
                        "breakthrough therapy", "clears fda"]),
    ("fda", 3, "bear", ["fda reject", "clinical hold", "trial fail", "phase 3 fail",
                        "fails to meet"]),
    ("guidance", 2, "bull", ["raises guidance", "raises outlook", "boosts forecast",
                             "lifts guidance", "above estimates"]),
    ("guidance", 3, "bear", ["cuts guidance", "lowers outlook", "slashes forecast",
                             "warns", "profit warning", "below estimates"]),
    ("earnings", 2, "bull", ["beats", "tops estimates", "record revenue",
                             "earnings beat", "strong quarter"]),
    ("earnings", 2, "bear", ["misses", "disappoints", "earnings miss", "weak quarter"]),
    ("rating", 1, "bull", ["upgrade", "raised to buy", "initiates buy", "outperform",
                           "price target raised"]),
    ("rating", 1, "bear", ["downgrade", "cut to sell", "underperform",
                           "price target cut"]),
    ("regulatory", 2, "bear", ["investigation", "probe", "subpoena", "antitrust",
                               "sanction", "recall"]),
    ("legal", 2, "bear", ["lawsuit", "sued", "settlement", "fraud", "class action"]),
    ("exec_change", 1, "neutral", ["ceo resigns", "cfo steps down", "names new ceo",
                                   "appoints", "departure"]),
]


@dataclass
class ClassifiedHeadline:
    title: str
    category: str
    severity: int
    direction: str

    @property
    def is_catalyst(self) -> bool:
        return self.category != "noise" and self.severity >= 2


@dataclass
class CatalystContext:
    has_catalyst: bool = False
    direction: str = "neutral"     # net bull/bear/neutral
    sources: int = 0               # number of catalyst headlines
    top_category: Optional[str] = None
    max_severity: int = 0


def classify_headline(title: str) -> ClassifiedHeadline:
    t = title.lower()
    for category, severity, direction, patterns in _RULES:
        for p in patterns:
            if p in t:
                return ClassifiedHeadline(title, category, severity, direction)
    return ClassifiedHeadline(title, "noise", 1, "neutral")


def aggregate(headlines: List[str]) -> CatalystContext:
    """Aggregate a ticker's headlines into a single catalyst context. Requires
    >=1 severity>=2 headline to flag a catalyst; net direction by bull/bear count
    (anti-spoof: a single source still counts but the gate's 2-source hard floor
    applies downstream for large moves)."""
    classified = [classify_headline(h) for h in headlines]
    catalysts = [c for c in classified if c.is_catalyst]
    if not catalysts:
        return CatalystContext()
    bull = sum(1 for c in catalysts if c.direction == "bull")
    bear = sum(1 for c in catalysts if c.direction == "bear")
    direction = "bull" if bull > bear else ("bear" if bear > bull else "neutral")
    top = max(catalysts, key=lambda c: c.severity)
    return CatalystContext(has_catalyst=True, direction=direction,
                           sources=len(catalysts), top_category=top.category,
                           max_severity=top.severity)
