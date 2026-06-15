"""
HOOD DaBang — ADAPTIVE RISK GOVERNOR (risk as a reasoned, bounded variable).

The operator's instruction: don't hardcode a conservative number; make risk a
variable, reason about its impact, and let evidence move it — with profit as the
ultimate guardrail (which, over many trades, means NOT blowing up).

This governor computes the *current* per-trade risk fraction from:
  - proven edge        (Kelly from the journal; quarter-Kelly until 30 trades)
  - a ruin ceiling     (Monte-Carlo optimal fraction at the ruin tolerance)
  - drawdown state     (throttle toward the floor as drawdown deepens)
  - volatility state   (scale down when realised vol exceeds target)
  - maturity gate      (cannot exceed the nominal 1.5% until the edge is proven)
and clamps the result to [floor, absolute_max]. The absolute_max and the
catastrophic floor are the immutable survival bounds; everything between them is
the variable the system optimises.

Pure stdlib; reuses src.sizing and src.decision.monte_carlo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ..sizing.sizers import StrategyStats, kelly_risk_pct
from . import monte_carlo as mc


@dataclass
class RiskContext:
    stats: StrategyStats
    drawdown_from_ath: float = 0.0     # 0.0 .. 1.0
    realized_vol_20d: float = 0.0      # annualised; 0 => unknown, no vol throttle
    n_proven_trades: int = 0           # trades with this strategy
    ruin_recommended_fraction: Optional[float] = None  # cached MC result (optional)


@dataclass
class RiskDecision:
    fraction: float
    components: Dict[str, float] = field(default_factory=dict)
    reason: str = ""


class AdaptiveRiskGovernor:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.a = cfg["adaptive_risk"]

    def _dd_throttle(self, dd: float) -> float:
        """Linear throttle: 1.0 above start threshold, 0.0 at the full threshold."""
        start, full = self.a["dd_throttle_start_pct"], self.a["dd_throttle_full_pct"]
        if dd <= start:
            return 1.0
        if dd >= full:
            return 0.0
        return 1.0 - (dd - start) / (full - start)

    def _vol_throttle(self, realized_vol: float) -> float:
        if realized_vol <= 0:
            return 1.0
        target = self.cfg["sizing"]["vol_target_annualized"]
        return min(self.cfg["sizing"]["vol_scalar_max"], target / realized_vol)

    def ruin_ceiling(self, ctx: RiskContext) -> float:
        """The MC ruin-constrained optimal fraction for this strategy's edge.
        Cached value preferred (MC is heavier); else computed from stats."""
        if ctx.ruin_recommended_fraction is not None:
            return ctx.ruin_recommended_fraction
        s = ctx.stats
        if s.n_trades < 5 or s.avg_loss_dollars <= 0:
            return self.a["nominal_pct"]
        p = s.win_rate
        win_R = s.avg_win_dollars / s.avg_loss_dollars
        rec = mc.optimal_risk_fraction(
            p, win_R, 1.0,
            ruin_tolerance=self.a["ruin_tolerance"],
            hard_cap=self.a["absolute_max_pct"],
            start_equity=self.cfg["account"]["starting_capital_usd"],
            catastrophic_floor=self.cfg["risk"]["catastrophic_halt_equity_usd"],
            n_paths=600,  # lighter for runtime; weekly job runs the full sweep
        )
        return rec.recommended_fraction

    def decide(self, ctx: RiskContext) -> RiskDecision:
        if not self.a["enabled"]:
            f = self.cfg["risk"]["per_trade_risk_pct"]
            return RiskDecision(f, {"static": f}, "adaptive_risk disabled; static cap")

        # half-Kelly, capped at the adaptive ceiling (2.5%) — NOT the 1.5% brief
        # cap — so a proven edge can size up to the survival bound.
        kelly = kelly_risk_pct(ctx.stats, self.cfg, cap_pct=self.a["absolute_max_pct"])
        ruin_cap = self.ruin_ceiling(ctx)
        dd_mult = self._dd_throttle(ctx.drawdown_from_ath)
        vol_mult = self._vol_throttle(ctx.realized_vol_20d)

        # base candidate: the smaller of proven Kelly and the ruin ceiling
        base = min(kelly, ruin_cap)
        # maturity gate: until proven, cannot exceed the nominal baseline
        if ctx.n_proven_trades < self.a["scale_up_requires_trades"]:
            base = min(base, self.a["nominal_pct"])

        adjusted = base * dd_mult * vol_mult

        # clamp to immutable survival bounds
        floor, cap = self.a["floor_pct"], self.a["absolute_max_pct"]
        final = max(floor, min(adjusted, cap)) if adjusted > 0 else floor
        # if drawdown throttle drove it to zero, respect that (defensive crouch)
        if dd_mult == 0.0:
            final = floor

        comp = {
            "kelly": round(kelly, 5), "ruin_cap": round(ruin_cap, 5),
            "dd_mult": round(dd_mult, 3), "vol_mult": round(vol_mult, 3),
            "base": round(base, 5), "final": round(final, 5),
        }
        reason = (f"f={final:.4f} = clamp(min(kelly={kelly:.4f}, ruin_cap={ruin_cap:.4f})"
                  f" * dd={dd_mult:.2f} * vol={vol_mult:.2f}) into [{floor},{cap}]")
        return RiskDecision(final, comp, reason)
