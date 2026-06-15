"""
HOOD DaBang — weekly/monthly meta-review (Brief §16 Sunday 18:00, §12).

Ties the self-improvement loop into a schedulable routine: session/week reflection,
Discoverer pattern-mining -> falsifiable hypotheses, memory consolidation,
strategy reallocation by per-regime expectancy, and BOUNDED conviction-floor
tuning (65-80, logged, shadow-first). Never touches the bedrock (recursive
constraint); floor changes stay inside the configured bounds.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .agents.reflector import Reflector, SessionReflection
from .agents.discoverer import Discoverer, DiscoveredPattern
from .decision.hypothesis import Hypothesis


@dataclass
class WeeklyReport:
    session: SessionReflection
    patterns: List[DiscoveredPattern]
    hypotheses: List[Hypothesis]
    reallocation: Dict[str, float]
    memory_consolidation: Dict[str, int]
    proposed_floor: float
    floor_change_reason: str
    notes: str = ""


class WeeklyReview:
    def __init__(self, cfg, journal=None, memory=None, reflector: Reflector = None,
                 discoverer: Discoverer = None, registry=None):
        self.cfg = cfg
        self.journal = journal
        self.memory = memory
        self.reflector = reflector or Reflector()
        self.discoverer = discoverer or Discoverer()
        self.registry = registry

    def _closed_trades(self) -> List[dict]:
        if self.journal is None:
            return []
        rows = self.journal.conn.execute(
            "SELECT strategy, market_regime, pnl_r, good_or_bad_loss FROM trades "
            "WHERE exit_ts IS NOT NULL").fetchall()
        return [{"strategy": r[0], "market_regime": r[1], "pnl_r": r[2] or 0.0,
                 "good_or_bad_loss": r[3]} for r in rows]

    def reallocate(self, trades: List[dict]) -> Dict[str, float]:
        """Per-strategy expectancy across the week -> normalized weights."""
        by_strat: Dict[str, List[float]] = defaultdict(list)
        for t in trades:
            by_strat[t["strategy"]].append(t["pnl_r"])
        exps = {s: (sum(rs) / len(rs)) for s, rs in by_strat.items() if rs}
        # only positive-expectancy strategies get weight
        pos = {s: e for s, e in exps.items() if e > 0}
        total = sum(pos.values())
        if total <= 0:
            return {}
        return {s: round(e / total, 4) for s, e in pos.items()}

    def tune_floor(self, trades: List[dict]) -> tuple:
        """Bounded conviction-floor tuning. If trades that just cleared the floor
        underperform, raise it; if we're rejecting would-be winners, lower it.
        Stays within [floor_min, floor_max]; returns (new_floor, reason)."""
        c = self.cfg["conviction"]
        current = c["execution_floor"]
        lo, hi = c["floor_min"], c["floor_max"]
        if len(trades) < 10:
            return current, "insufficient sample; floor unchanged"
        exp = sum(t["pnl_r"] for t in trades) / len(trades)
        if exp < -0.05:
            return min(hi, current + 1), f"weekly expectancy {exp:+.2f}R < 0 -> raise floor"
        if exp > 0.20:
            return max(lo, current - 1), f"strong expectancy {exp:+.2f}R -> lower floor slightly"
        return current, f"expectancy {exp:+.2f}R within band; floor unchanged"

    def run(self) -> WeeklyReport:
        trades = self._closed_trades()
        session = self.reflector.reflect_session(trades)
        patterns = self.discoverer.mine(trades)
        hypotheses = self.discoverer.to_hypotheses(patterns)
        realloc = self.reallocate(trades)
        consolidation = self.memory.consolidate() if self.memory else {}
        new_floor, reason = self.tune_floor(trades)

        notes = (f"{session.notes} | {len(patterns)} patterns, "
                 f"{len(hypotheses)} hypotheses queued for the 5 gates. "
                 f"Floor: {self.cfg['conviction']['execution_floor']} -> {new_floor} "
                 f"({reason}).")
        return WeeklyReport(session, patterns, hypotheses, realloc, consolidation,
                            new_floor, reason, notes)
