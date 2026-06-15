"""
HOOD DaBang — falsifiable thesis schema (Brief §7.1).

A trade is only allowed if it can be expressed as a thesis with a stated
MECHANISM (why it should happen) and at least one INVALIDATION condition (when
we are wrong). The gap between thesis confidence and the historical base rate is
itself a Conviction-Gate warning.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Driver:
    evidence: str
    weight: float          # 0..1


@dataclass
class Thesis:
    ticker: str
    direction: str                       # "long" | "short"
    claim: str
    mechanism: str
    invalidation: List[str] = field(default_factory=list)
    drivers: List[Driver] = field(default_factory=list)
    expected_path: str = ""
    confidence: float = 0.5
    base_rate: Optional[float] = None
    time_horizon_minutes: int = 60
    strategy: str = ""

    @property
    def is_falsifiable(self) -> bool:
        """Must have a non-empty mechanism AND >=1 invalidation condition."""
        return bool(self.mechanism.strip()) and len([i for i in self.invalidation
                                                      if i.strip()]) >= 1

    @property
    def confidence_base_rate_gap(self) -> Optional[float]:
        """Overconfidence flag: confidence far above the historical base rate is
        a warning the Conviction Gate downweights."""
        if self.base_rate is None:
            return None
        return self.confidence - self.base_rate

    def id(self) -> str:
        payload = f"{self.ticker}|{self.direction}|{self.claim}|{self.mechanism}"
        return hashlib.sha1(payload.encode()).hexdigest()[:16]

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, sort_keys=True)
