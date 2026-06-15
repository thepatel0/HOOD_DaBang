# HOOD DaBang

An autonomous, multi-agent, hybrid **AI + rules** equities trading desk in
software that prizes trade **quality over quantity**. Built to the v7 FINAL brief
(`HOOD_DABANG_v7_FINAL.md`). Capital $1,500, US equities, one operator who will
not watch the screen.

> **Status: BUILD IN PROGRESS — paper/build only.** No real capital. The system
> is not "done" until all 12 Definition-of-Done items (brief §35) are green.
> See `data/build_status.md`.

## What runs today (Phase 0 — token-free deterministic bedrock)
Pure standard library, **zero pip installs, $0, zero LLM tokens**:
- `src/config.py` — canonical parameters (§32) + fail-closed validation
- `src/token_decision_engine.py` — the **$0-first routing brain**: decides what
  can be done for free in Python vs what genuinely needs a paid model, and
  refuses to escalate when the budget says no
- `src/event_bus.py` — priority FIFO; `KillEvent` jumps the queue
- `src/db.py` — SQLite WAL schema (§33)
- `src/risk.py` — the risk gate; every order passes through (§13)
- `src/killswitch.py` — the killswitch registry (§14 + §30.7)
- `src/conviction/` — Conviction Gate Stage-1 scorecard + hard floors + rank (§6)
- `src/sizing/` — Kelly / vol-target / conviction-scaled sizing (§10)

## Run the tests (no installs needed)
```bash
cd hood-dabang
make test          # or:
PYTHONPATH=. python3 -m unittest discover -s tests -t .
```
Phase 0: **69 tests, all green.**

## Token philosophy (why this is cheap)
Everything deterministic — math, parsing, rules, ML inference — is **Tier 0**
local Python and never touches a model. Paid models are reached only for the top
1-3 Conviction-Gate survivors, cheapest-tier-first, cache-first, budget-gated.
The brief targets ~$1.80/day of LLM spend against a $5/day hard killswitch.

## Roadmap
Phases 1-7 in `data/build_status.md`: Tier-0 analysts (numpy/hmmlearn) → data
feeds → MCP discovery + execution → LLM agents → 19 strategies behind the five
validation gates → backtest/memory/self-improvement → dashboard + ops + chaos
tests → paper day → reduced-capital live ramp ($300 first, not $1,500).

## Safety stance
The rule layer is bedrock; the AI layer is judgment *inside* it. An LLM can never
override a risk cap, a killswitch, a position limit, a budget cap, or a
Conviction-Gate floor. Live capital only after §35 is fully green and the
operator explicitly approves a paper day's results.
