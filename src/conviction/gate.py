"""
HOOD DaBang — Conviction Gate (Brief 6, 26.1).

Stage 1 (here, fully implemented, $0): score every SignalEvent, apply hard
floors regardless of score, keep survivors above the stage-1 floor, rank, and
advance ONLY the top N (default 3) to the paid LLM pipeline. Every decision is
returned with a reason for logging to data/conviction_log/.

Stage 2 (full verdict) combines deterministic + debate + thesis + calibration;
its formula is implemented in `stage2_verdict` and consumes LLM outputs (so it
runs only on the 1-3 survivors).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .scorecard import Signal, score, hard_floor_reject


@dataclass
class GateDecision:
    ticker: str
    strategy: str
    deterministic_score: float
    advanced: bool
    reason: str
    rank: Optional[int] = None


@dataclass
class GateResult:
    advancing: List[Signal] = field(default_factory=list)
    decisions: List[GateDecision] = field(default_factory=list)

    @property
    def highest_not_taken(self) -> Optional[GateDecision]:
        rejected = [d for d in self.decisions if not d.advanced and d.deterministic_score > 0]
        return max(rejected, key=lambda d: d.deterministic_score, default=None)


class ConvictionGate:
    def __init__(self, cfg: dict):
        c = cfg["conviction"]
        self.weights = c["scorecard_weights"]
        self.stage1_floor = c["stage1_hard_floor"]
        self.execution_floor = c["execution_floor"]
        self.max_candidates = c["max_candidates_to_llm"]
        self.verdict_weights = c["verdict_weights"]
        self._floor_bump = 0.0  # transient: revenge-suppression / near-close

    # ---- runtime floor adjustments (Brief 6.6) ---------------------------- #
    def set_floor_bump(self, bump: float) -> None:
        """+5 for 30 min after a loss, +3 after 15:00 ET, etc. Applied to the
        EXECUTION floor (Stage 2), per the brief."""
        self._floor_bump = bump

    @property
    def effective_execution_floor(self) -> float:
        return self.execution_floor + self._floor_bump

    # ---- Stage 1 ---------------------------------------------------------- #
    def stage1(self, signals: List[Signal]) -> GateResult:
        result = GateResult()
        survivors: List[Signal] = []

        for sig in signals:
            score(sig, self.weights)
            reason = hard_floor_reject(sig)
            if reason is not None:
                sig.hard_floor_reason = reason
                result.decisions.append(GateDecision(
                    sig.ticker, sig.strategy, sig.det_score, False,
                    reason=f"hard_floor:{reason}"))
                continue
            if sig.det_score < self.stage1_floor:
                result.decisions.append(GateDecision(
                    sig.ticker, sig.strategy, sig.det_score, False,
                    reason=f"below_stage1_floor({self.stage1_floor})"))
                continue
            survivors.append(sig)

        # rank survivors by deterministic score, advance top N
        survivors.sort(key=lambda s: s.det_score, reverse=True)
        for rank, sig in enumerate(survivors, start=1):
            if rank <= self.max_candidates:
                result.advancing.append(sig)
                result.decisions.append(GateDecision(
                    sig.ticker, sig.strategy, sig.det_score, True,
                    reason="advanced_to_llm", rank=rank))
            else:
                result.decisions.append(GateDecision(
                    sig.ticker, sig.strategy, sig.det_score, False,
                    reason=f"ranked_{rank}_below_top_{self.max_candidates}",
                    rank=rank))
        return result

    # ---- Stage 2 (Brief 6.3) --------------------------------------------- #
    def stage2_verdict(self, deterministic_score: float, bull_conf: float,
                       bear_conf: float, thesis_quality: float,
                       source_calibration: float) -> Dict[str, float]:
        """Combine the four Stage-2 inputs into a final conviction score [0,100].
        bull/bear/thesis/calibration are 0..1; deterministic_score is 0..100."""
        w = self.verdict_weights
        debate_margin = max(0.0, bull_conf - bear_conf)  # 0..1
        final = (
            w["deterministic"] * deterministic_score
            + w["debate_margin"] * (debate_margin * 100.0)
            + w["thesis_quality"] * (thesis_quality * 100.0)
            + w["source_calibration"] * (source_calibration * 100.0)
        )
        return {
            "final_conviction": round(final, 4),
            "passes": final >= self.effective_execution_floor,
            "execution_floor": self.effective_execution_floor,
        }
