"""
HOOD DaBang — Insight Engine (Brief §7, §26.2).

Builds a falsifiable Thesis for each Conviction-Gate survivor. Deterministic
fallback first (so a textbook setup still gets a rule-based thesis at $0 during
budget-pause); optional LLM enrichment (Tier 2 Sonnet). Returns None (=> no
trade) if it cannot construct a falsifiable thesis — mechanism + >=1 invalidation
are mandatory.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from ..strategies.base import Setup, MarketState
from .thesis import Thesis, Driver


# Mechanism templates per strategy (the WHY, not just "indicators align").
_MECHANISMS: Dict[str, str] = {
    "orb": ("Overnight information expresses as a directional move once the opening "
            "range resolves; participants chase the breakout on elevated volume, so "
            "the move tends to persist for 1-2 hours."),
    "vwap_reversion": ("Algorithmic flow overextends price away from session VWAP; "
                       "with no fresh catalyst, mean-reversion pulls it back to VWAP."),
    "gap_fill": ("A catalyst-less gap leaves an unfilled imbalance; liquidity providers "
                 "fade it and price reverts toward the prior close."),
    "momentum": ("Unusual volume signals unusual interest; pullbacks into a rising EMA "
                 "attract continuation flow."),
    "pairs": ("Two historically cointegrated names diverged; the spread mean-reverts "
              "as relative value re-asserts, independent of market direction."),
}
_DEFAULT_MECHANISM = ("A multi-factor confluence setup: the entry trigger, regime fit, "
                      "and volume confirmation jointly imply a short-horizon edge.")

# Conservative default base rates by strategy (overridden by journal/memory).
_DEFAULT_BASE_RATE = {"orb": 0.50, "vwap_reversion": 0.55, "gap_fill": 0.62,
                      "momentum": 0.48, "pairs": 0.58}


class InsightEngine:
    def __init__(self, cfg: dict, llm_client=None,
                 base_rates: Optional[Dict[str, float]] = None):
        self.cfg = cfg
        self.llm = llm_client
        self.base_rates = base_rates or {}

    def base_rate_for(self, strategy: str) -> Optional[float]:
        if strategy in self.base_rates:
            return self.base_rates[strategy]
        return _DEFAULT_BASE_RATE.get(strategy)

    # ----- public -------------------------------------------------------- #
    def build(self, setup: Setup, ms: MarketState, *, use_llm: bool = False,
              is_gate_survivor: bool = True) -> Optional[Thesis]:
        if use_llm and self.llm is not None:
            t = self._llm_build(setup, ms, is_gate_survivor)
            if t is not None and t.is_falsifiable:
                return t
            # fall through to deterministic on degrade / parse failure
        t = self._deterministic(setup, ms)
        return t if t.is_falsifiable else None

    # ----- deterministic ------------------------------------------------- #
    def _deterministic(self, setup: Setup, ms: MarketState) -> Thesis:
        direction = setup.side
        mech = _MECHANISMS.get(setup.strategy, _DEFAULT_MECHANISM)

        invalidation: List[str] = [f"loses the stop at {setup.stop_price:.2f}"]
        if ms.vwap is not None:
            side_word = "below" if direction == "long" else "above"
            invalidation.append(f"closes {side_word} VWAP ({ms.vwap:.2f})")
        if setup.strategy == "orb" and ms.opening_range_high and ms.opening_range_low:
            lvl = ms.opening_range_high if direction == "long" else ms.opening_range_low
            back = "below" if direction == "long" else "above"
            invalidation.append(f"closes back {back} the opening range edge ({lvl:.2f})")
        invalidation.append("SPY/QQQ reverses the broad-market tape against the position")

        drivers = [Driver(f"{k}={v}", round(min(1.0, v / 100.0), 2))
                   for k, v in setup.factors.items() if v >= 60]

        # confidence from the mean of the conviction factors, lightly damped
        mean_factor = sum(setup.factors.values()) / max(1, len(setup.factors))
        confidence = round(min(0.9, 0.4 + 0.5 * (mean_factor / 100.0)), 3)

        tgt = setup.targets[0][0] if setup.targets else setup.entry_price
        claim = (f"{ms.ticker} {direction} from {setup.entry_price:.2f} toward "
                 f"{tgt:.2f} (>= {setup.reward_risk:.1f}R)")
        expected = (f"Within ~{setup.expected_hold_min} min, price should hold the "
                    f"{'breakout' if 'orb' in setup.strategy else 'entry'} side and "
                    f"reach the first target before invalidation.")

        return Thesis(
            ticker=ms.ticker, direction=direction, claim=claim, mechanism=mech,
            invalidation=invalidation, drivers=drivers, expected_path=expected,
            confidence=confidence, base_rate=self.base_rate_for(setup.strategy),
            time_horizon_minutes=setup.expected_hold_min, strategy=setup.strategy)

    # ----- LLM-backed ---------------------------------------------------- #
    def _llm_build(self, setup: Setup, ms: MarketState,
                   is_gate_survivor: bool) -> Optional[Thesis]:
        system = (
            "You are the Insight Engine for a disciplined trading desk. Given a "
            "candidate setup and market state, return ONLY JSON with keys: claim, "
            "mechanism (WHY this should happen, causal — not 'indicators align'), "
            "invalidation (array of conditions that prove the thesis wrong), "
            "expected_path, confidence (0-1). If you cannot state a real mechanism "
            "and at least one invalidation, return {\"pass\": true}.")
        ctx = {
            "ticker": ms.ticker, "strategy": setup.strategy, "side": setup.side,
            "entry": setup.entry_price, "stop": setup.stop_price,
            "targets": setup.targets, "factors": setup.factors,
            "vwap": ms.vwap, "regime": ms.regime, "rvol": ms.rvol,
            "opening_range": [ms.opening_range_low, ms.opening_range_high],
        }
        resp = self.llm.call(
            "insight_thesis", "insight_engine", system,
            [{"role": "user", "content": json.dumps(ctx)}],
            is_gate_survivor=is_gate_survivor, max_tokens=700)
        if not resp.spent or not resp.text:
            return None
        try:
            data = json.loads(resp.text)
        except (ValueError, TypeError):
            return None
        if data.get("pass"):
            return None
        return Thesis(
            ticker=ms.ticker, direction=setup.side,
            claim=data.get("claim", ""), mechanism=data.get("mechanism", ""),
            invalidation=list(data.get("invalidation", [])),
            expected_path=data.get("expected_path", ""),
            confidence=float(data.get("confidence", 0.5)),
            base_rate=self.base_rate_for(setup.strategy),
            time_horizon_minutes=setup.expected_hold_min, strategy=setup.strategy)
