# HOOD DaBang — Build Status Ledger (Brief §31.3)

Resumable: a new session reads this and continues from the first unfinished item.
**Last updated: session 4 · 266 tests green · 20 commits.**
Run tests: `make test`  ·  Demos: `make demo` and
`PYTHONPATH=. .venv/bin/python -m src.run_live --paper --once`

## DONE & TESTED (every item has passing acceptance tests)

### Bedrock ($0, pure stdlib)
- config.py (canonical params §32 + fail-closed validation)
- token_decision_engine.py ($0-first routing brain)
- event_bus.py (priority FIFO, KillEvent jumps)
- db.py (SQLite WAL schema §33)
- risk.py (risk gate, all caps, adaptive authorization)
- killswitch.py (deterministic subset of 29)
- conviction/ (Stage-1 scorecard + hard floors + rank; Stage-2 verdict)
- sizing/ (Kelly / vol / conviction-scaled / min-of-constraints)

### Decision / falsification (operator's risk philosophy)
- decision/hypothesis.py (FalsificationEngine, permutation test)
- decision/monte_carlo.py (ruin sim + ruin-constrained optimal risk)
- decision/adaptive_risk.py (risk as a bounded, optimised variable)

### Strategies + Tier-0 analysts
- strategies/base.py + registry.py (5-gate live-lock, §30.1 router)
- strategies: orb, vwap_reversion, momentum (3 of 19)
- analysts_local/technical.py (numpy indicators)
- analysts_local/regime.py (HMM + RandomForest ensemble)

### Execution + data
- mcp_client.py (typed, schema-validated) + mcp_http.py (live JSON-RPC transport)
- execution.py (atomic entry, idempotent, conviction/thesis gates)
- reconciliation.py · journal.py (persistence)
- data_feeds/bars.py (cached yfinance, graceful degradation)

### Backtest + validation
- backtest/engine.py (event-driven, no-look-ahead) + stats.py
- backtest/validation.py (walk-forward, bootstrap PBO, Deflated Sharpe, OOS)

### LLM layer + memory
- llm_client.py + llm_budget.py (tier-aware, budget, ledger, cache discount)
- insight/ (falsifiable thesis, deterministic + LLM)
- agents/ (bull/bear debate, trader, PM — structured, fail-closed)
- memory/store.py (4 layers, recency×relevance×importance, consolidation)

### Orchestration + ops + monitoring
- controller.py (full pipeline; rules mode AND full LLM mode)
- monitor/dashboard.py (rich) · monitor/notifications.py (osascript)
- ops/selftest.py (runtime invariant checks) · ops/lifecycle.py (startup gate, launchd)
- run_live.py (entry point; paper default, live operator-armed only)
- scripts/demo_day.py (`make demo`)
- test_integration.py + chaos + full-mode pipeline tests

## STILL TO BUILD (breadth on a proven core)
- 16 remaining strategies (gap fill/go, earnings reaction, catalyst scalp, range
  compression, hourly sweep, engulfing, sector rotation, short squeeze, pairs,
  + 5 swing strategies)
- Data feeds: news RSS, SEC EDGAR Form 4, FRED, earnings calendar, FINRA short
- Analysts: microstructure, insider
- Agents: news, sentiment, macro, fundamentals, reflector, discoverer, meta-learner, judge
- Self-improvement: golden samples, judge harness, meta-prompter, shadow mode, A/B
- Slash-command operator interface (§22)
- Live-feed killswitches (#4 MCP, #6 stale, #11 quote-spike, #13 P&L velocity)

## OPERATOR ACTIONS NEEDED
1. **GitHub push auth** — local repo has 20 commits; push needs `gh auth login`
   or a PAT (anonymous read works; push prompted for credentials).
2. **Live MCP §34 discovery** — before any real order, run discover() against the
   real server to confirm tool names; the wrapper halts on mismatch.

## Definition of Done (§35): PAPER/BACKTEST-ONLY until all 12 items + operator
approval. Going live with real capital is the operator's switch, never the agent's.
