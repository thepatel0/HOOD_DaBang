# HOOD DaBang

An autonomous, multi-agent, hybrid **AI + rules** US-equities trading desk that
prizes trade **quality over quantity**. Built to the v7 FINAL brief (`BRIEF.md`).
Capital $1,500, Robinhood Agentic MCP, one operator who will not watch the screen.

> **Status: architecture COMPLETE — 430 tests green.** PAPER/BACKTEST-ONLY until
> the 12-point Definition of Done (§35) is satisfied + operator approval. Going
> live with real capital is the operator's switch, never the agent's.

## Quick start
```bash
cd hood-dabang
make test          # 430 tests (uses the 3.13 venv)
make demo          # one synthetic day through the full pipeline
PYTHONPATH=. .venv/bin/python -m src.run_live --paper --once   # real data, paper
PYTHONPATH=. .venv/bin/python scripts/validate_strategy.py --ticker SPY --strategy orb
```

## What it is
A trading desk in software: ~13 specialized agents (most deterministic Python, a
few LLM-backed) coordinated by an event-driven controller, with layered memory, a
self-improvement loop, hard survival rails, a **Conviction Gate** that is
comfortable doing nothing, and an **Insight Engine** that requires every trade to
be a falsifiable thesis (mechanism + invalidation) before entry.

## Architecture (all built + tested)
- **Bedrock ($0, deterministic):** config+validation, token decision engine, event
  bus, SQLite-WAL DB, risk gate, 29-killswitch registry, Conviction Gate (Stage
  1+2), Kelly/vol/conviction sizing.
- **Risk as a variable:** `AdaptiveRiskGovernor` = min(half-Kelly, Monte-Carlo
  ruin-ceiling) × drawdown/vol throttles, bounded [0.1%, 2.5%], maturity-gated.
  Every change must survive the `FalsificationEngine` (reject the null, p<0.05).
- **19 strategies** + registry (five-gate live-lock, signal router).
- **Tier-0 analysts:** technical (numpy), microstructure, insider, regime (HMM+RF).
- **Execution:** schema-validated MCP client + live JSON-RPC HTTP transport +
  atomic-entry handler (2s stop-or-flatten) + reconciliation.
- **Data feeds:** yfinance bars, news RSS, SEC Form 4, FRED, earnings — cached,
  degrade-safe.
- **Backtest + 5 validation gates** (walk-forward, bootstrap PBO, Deflated Sharpe,
  OOS) — strictly no-look-ahead.
- **LLM layer:** tier-aware client + budget + ledger; insight, news, sentiment,
  macro, fundamentals, bull/bear debate, trader, PM, reflector, discoverer,
  meta-learner — all structured-output, fail-closed, prompt-injection-defended.
- **Memory:** 4 layers, recency×relevance×importance, weekly consolidation.
- **Self-improvement:** golden samples, judge, shadow mode, meta-prompter, and the
  **recursive constraint** (can never modify risk/killswitch/reconciliation/tests/
  gate-floors — structurally enforced).
- **Orchestration:** controller (rules mode AND full LLM mode), research pipeline,
  screener, weekly review.
- **Monitoring/ops:** rich dashboard, notifications, P&L-velocity/feed/order-rate
  health monitors, self-test suite, startup gating, launchd, operator slash commands.

## Token philosophy
Everything deterministic — math, parsing, rules, ML inference — is **Tier 0** local
Python ($0). Paid models are reached only for the top 1-3 Conviction-Gate
survivors, cheapest-tier-first, cache-first, budget-gated. Target ~$1.80/day vs a
$5/day hard killswitch. The `TokenDecisionEngine` makes this an auditable runtime
decision, not a static rule.

## The honesty mechanism
On **real SPY data**, a raw ORB strategy fails all four backtest gates — and the
system correctly **refuses to let it trade**. Backtest Sharpe predicts live at
R²<0.025, so most strategies *should* fail; the five gates are how you find out
before risking capital. Run `scripts/validate_strategy.py` to test any strategy.

## Before live (operator)
1. Push to GitHub (`gh auth login`, then `git push`).
2. §34 MCP discovery: `client.discover()` against the real server; set
   `ROBINHOOD_MCP_TOKEN`. The wrapper halts on tool-name mismatch.
3. Prove edges through the five gates on real data; only gate-passers go `live`.
4. Work the 12-point Definition of Done, then `run_live --live --arm-live`.

## Safety stance
The rule layer is bedrock; the AI layer is judgment *inside* it. An LLM can never
override a risk cap, killswitch, position limit, budget cap, or Conviction-Gate
floor. See `data/build_status.md` for the full component ledger.
