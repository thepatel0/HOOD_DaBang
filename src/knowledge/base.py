"""
HOOD DaBang — shared KnowledgeBase (the paper -> production bridge).

The ONLY thing that crosses the paper/production isolation boundary. Raw paper
trades, journal, equity, and memory stay sandboxed; but a PATTERN that survives
falsification in paper graduates here as VALIDATED KNOWLEDGE with provenance
(source, sample size, p-value). Production reads validated patterns to tilt
conviction/allocation; it never sees raw paper data.

A pattern is only ever written after `FalsificationEngine` rejects its null —
so the knowledge base cannot be polluted by noise or overfit paper runs.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from ..decision.hypothesis import Hypothesis, FalsificationEngine

KNOWLEDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_patterns (
  id TEXT PRIMARY KEY,
  segment TEXT,                -- e.g. "orb@bull_trend_low_vol"
  statement TEXT,
  expectancy_r REAL,
  n_observations INTEGER,
  p_value REAL,
  source TEXT,                 -- paper | live
  status TEXT,                 -- candidate | validated | retired
  created_ts REAL,
  updated_ts REAL
);
"""


@dataclass
class KnowledgePattern:
    id: str
    segment: str
    statement: str
    expectancy_r: float
    n_observations: int
    p_value: float
    source: str
    status: str


class KnowledgeBase:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(KNOWLEDGE_SCHEMA)
        self.conn.commit()
        self.engine = FalsificationEngine()

    def _upsert(self, p: KnowledgePattern) -> None:
        now = time.time()
        self.conn.execute(
            "INSERT INTO knowledge_patterns (id, segment, statement, expectancy_r, "
            "n_observations, p_value, source, status, created_ts, updated_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET expectancy_r=excluded.expectancy_r, "
            "n_observations=excluded.n_observations, p_value=excluded.p_value, "
            "status=excluded.status, updated_ts=excluded.updated_ts",
            (p.id, p.segment, p.statement, p.expectancy_r, p.n_observations,
             p.p_value, p.source, p.status, now, now))
        self.conn.commit()

    def validate_and_store(self, segment: str, statement: str,
                           treatment_samples: List[float], control_samples: List[float],
                           source: str = "paper", min_sample: int = 30) -> Optional[KnowledgePattern]:
        """Run the falsification test; store as VALIDATED only if the null is
        rejected (the change/edge is real). Otherwise nothing is written — noise
        never enters the knowledge base."""
        h = Hypothesis(id=f"kb:{segment}", statement=statement,
                       null_statement=f"{segment} has no real edge",
                       direction="greater", min_sample=min_sample)
        res = self.engine.evaluate(h, treatment_samples, control_samples)
        if not res.adopt:
            return None
        p = KnowledgePattern(
            id=f"kb:{segment}", segment=segment, statement=statement,
            expectancy_r=round(res.effect_size, 4), n_observations=len(treatment_samples),
            p_value=round(res.p_value, 4), source=source, status="validated")
        self._upsert(p)
        return p

    def retire(self, segment: str) -> None:
        self.conn.execute(
            "UPDATE knowledge_patterns SET status='retired', updated_ts=? "
            "WHERE id=?", (time.time(), f"kb:{segment}"))
        self.conn.commit()

    def validated_patterns(self) -> List[KnowledgePattern]:
        rows = self.conn.execute(
            "SELECT id, segment, statement, expectancy_r, n_observations, p_value, "
            "source, status FROM knowledge_patterns WHERE status='validated'").fetchall()
        return [KnowledgePattern(*r) for r in rows]

    def conviction_tilt(self, strategy: str, regime: str) -> float:
        """A small, bounded tilt (+/- points) production applies to a strategy's
        conviction in a regime, based on validated knowledge. Bounded to +/-5 so
        learned tilts can never dominate the bedrock scorecard."""
        seg = f"{strategy}@{regime}"
        row = self.conn.execute(
            "SELECT expectancy_r FROM knowledge_patterns WHERE id=? AND status='validated'",
            (f"kb:{seg}",)).fetchone()
        if not row:
            return 0.0
        exp = row[0]
        return max(-5.0, min(5.0, exp * 10.0))   # 0.5R edge -> +5 tilt, capped
