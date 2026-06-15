# Build note — Phase 0 bedrock (self-verification against spec)

## Key architectural decision (mine, beyond the brief)
The brief assumes Python 3.11 and a heavy dependency set (numpy, pydantic,
hmmlearn, sentence-transformers, ...). This machine has **system Python 3.9.6**.
Rather than block the entire build on environment setup, I split the system at a
natural seam the brief already implies (Tier 0 vs Tiers 1-3):

- **Bedrock = pure stdlib.** The safety-critical, deterministic, $0 core (risk
  gate, killswitches, conviction Stage-1, sizing, event bus, DB, config, the
  token decision engine) uses ONLY the standard library. It runs today, with no
  pip install, and reruns daily as a reusable component with zero tokens — the
  operator's explicit requirement.
- **Heavier deps deferred** to the Tier-0-analyst and LLM phases where they are
  genuinely needed (numpy for indicators, hmmlearn for the regime model,
  anthropic for the agents).

This is the brief's "degrade, don't die" principle applied to the *build* itself:
the survival layer is the layer with the fewest moving parts.

## Requirements coverage (self-check, Brief §26 / §31.4)
- **risk.py (§26.4):** every cap enforced individually; returns ALL violations;
  fail-closed on structural problems; override relaxes only soft caps, never the
  catastrophic halt / thesis-less / conviction-less rules. ✅
- **killswitch.py (§14/30.7):** deterministic, state-evaluable conditions
  implemented (1,2,3,5,8,9,10,12,14,15,21,22,25,26,27,28,29). Live-feed-dependent
  ones (4 MCP, 6 stale feed, 7 DB integrity, 11 quote spike, 13 P&L velocity,
  16 feature-flag, 17 time, 18 parity, 19 memory, 20 calibration, 23 outage,
  24 cache) register through the same `evaluate()` interface once their data
  sources exist. ⚠️ partial-by-design — noted to operator.
- **conviction/gate.py (§26.1):** Stage-1 scores 0-100, hard floors override
  score, ranks, advances top 1-3, logs every decision with reason,
  `highest_not_taken` surfaced for the dashboard; Stage-2 verdict formula matches
  §6.3 exactly. ✅
- **sizing (§26.14):** half-Kelly (quarter/0.5% when <30 trades), 1.5% cap, vol
  targeting, conviction scaling 60→100%, final = min of constraints. ✅
  ⚠️ correlation cap is implemented as a notional-headroom helper; full
  cross-position 0.7-correlation collapse needs the positions table + a 60-day
  return matrix (Phase 1+). Noted.
- **token_decision_engine.py (operator requirement):** cache-first → tier-floor →
  gate-gating → budget-aware degrade. Pure function, fully tested. ✅

## What is explicitly NOT done yet (honesty over optimism, §35)
No live trading is possible: no MCP wrapper, no data feeds, no strategies have
passed the five validation gates, no paper day has run. Per §35 the system is
PAPER-ONLY (in fact build-only) until all 12 Definition-of-Done items are green.
