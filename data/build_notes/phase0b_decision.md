# Build note — Decision layer (operator's risk philosophy as code)

## What the operator asked for
"Risk should be a variable. Make smart, thought-through decisions; start with the
null hypothesis that your decision is WRONG, then find a way to prove it wrong —
if you can, it's worth trying. Making profit is the most important guardrail."

## What I built (3 components, 15 tests, pure stdlib)
- **hypothesis.py — FalsificationEngine.** Every consequential change (new
  strategy, risk-param tweak, prompt revision, floor change) is framed as a
  hypothesis with an explicit null. Adoption requires REJECTING the null via a
  permutation test (p<alpha), in the correct direction, with n>=min_sample.
  Default stance is REJECT the change — the burden of proof is on the change.
  Permutation/bootstrap (not t-test) because trade P&L is fat-tailed.
- **monte_carlo.py — ruin simulator + optimal_risk_fraction.** Answers "what
  could the impact be?" with a distribution: terminal-wealth percentiles, median
  log-growth, AND P(ruin). `optimal_risk_fraction` sweeps risk and returns the
  fraction maximising median terminal wealth SUBJECT TO P(ruin) <= tolerance.
- **adaptive_risk.py — AdaptiveRiskGovernor.** Risk per trade is now a VARIABLE:
  min(proven half-Kelly, MC ruin-ceiling) * drawdown_throttle * vol_throttle,
  clamped to [0.1%, 2.5%], gated so it can't exceed 1.5% until 30 proven trades.

## The key finding (empirical, reproducible)
For a proven 55%/1.5R edge: full Kelly = 25% (absurdly high); within a 1% ruin
tolerance and a 2.5% hard cap, the optimal is 2.5%. Growth rises monotonically
with bet size until the ruin cliff (~3%+). CONCLUSION: more aggression than the
brief's flat 1.5% is justified — but ONLY on a proven edge, and the hard cap at
2.5% (vs 25% full Kelly) is deliberate insurance against estimation error in p.

## Null-hypothesis applied to the design decision itself
- Hypothesis: "Allowing adaptive risk up to 2.5% (vs flat 1.5%) increases growth."
- Null: "It does not / it raises ruin risk."
- Test: the MC sweep. Within [0,2.5%], P(ruin)=0 at this edge while median
  terminal rises 2.4x from 1.5%->2.5%. Null rejected for PROVEN edges; the
  maturity gate (30-trade requirement) protects the UNPROVEN case where the null
  would stand. => Adopt, bounded.

## Immutable bounds (cannot be tuned away)
absolute_max_pct (2.5%), catastrophic floor ($1,050), the no-thesis / no-
conviction rejection. These are the survival rails the optimiser is not allowed
to cross.
