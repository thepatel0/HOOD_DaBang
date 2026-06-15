# HOOD DABANG — COMPLETE MASTER PROMPT — v7 FINAL (LATEST)
**An autonomous, multi-agent, hybrid AI + rules stock-trading system that prizes trade _quality_ over trade _quantity_.**
**This is the latest and most complete version. It supersedes all prior versions (v1-v6). Use this file.**
**Build governance: Sections 31-35 instruct the Opus 4.8 build agent to research each component with subagents, build to contract, run tests and refuse to advance on failure, and meet a 12-point Definition of Done before any live capital.**
**Built for Claude Code with Opus 4.8 (Max mode). Connected to Robinhood Agentic MCP at `https://agent.robinhood.com/mcp/trading`.**
**Capital: $1,500. Asset scope: US equities. Operator: one human with a full-time job who will not watch the screen.**

> This is the complete, self-contained specification. It does not depend on any other file. Everything — architecture, all 19 strategies with full specs, all 28 failure modes with defenses, the Conviction Gate, the Insight Engine, token economics, the operational lifecycle, per-component requirements with acceptance tests, and the bootstrap sequence — is inline below. Save this as `BRIEF.md` and drop it into Claude Code.

---

## TABLE OF CONTENTS

0. What Hood Dabang is, and the philosophy
1. Prime directives
2. Account, regulatory & practical context
3. Token economics — the four-tier architecture
4. System architecture (event-driven, hybrid AI + rules)
5. The agents — full roles, inputs, outputs, guardrails
6. The Conviction Gate — quality over quantity
7. The Insight Engine — falsifiable theses
8. Strategy library — all 19 strategies, full specs
9. Strategy validation — the five gates
10. Position sizing — Kelly, volatility-targeted, correlation-capped, conviction-scaled
11. Layered memory architecture
12. Self-improvement architecture
13. Risk management — the non-negotiable layer
14. Killswitches — all 26
15. Self-tests — all 26
16. The daily rhythm
17. Data sources — all free, with graceful degradation
18. The 28 AI failure modes + defenses
19. Honest benchmarks
20. Monitoring — the terminal dashboard
21. Notifications
22. Operator interface — slash commands
23. Operational lifecycle — start, stop, recover, schedule
24. What to read — curriculum
25. Will this work? — operator's honest checklist
26. Per-component detailed requirements & acceptance tests
27. Bootstrap sequence
28. Final words to the controller
29. Changelog

### Bootstrap (do this first)

```bash
mkdir -p ~/hood-dabang && cd ~/hood-dabang
# Save this file as BRIEF.md
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
claude --model opus
```
Then, in Claude Code:
> "You are building Hood Dabang. Read BRIEF.md cover to cover. Ask me clarifying questions before any code. Then execute Section 27 (Bootstrap Sequence) with explicit operator approval at every `[ASK]` checkpoint. Run Section 15 (Self-Tests) green before any live capital."

---

## 0. WHAT HOOD DABANG IS, AND THE PHILOSOPHY

Hood Dabang is a trading desk in software: ~13 specialized agents (most deterministic Python, a few LLM-backed) coordinated by an event-driven controller, with layered memory, a self-improvement loop, hard survival rails, a **Conviction Gate** that makes the system comfortable doing nothing, and an **Insight Engine** that requires every trade to be a falsifiable thesis.

### Architectural lineage — what was learned from each real system

- **TradingAgents** (Tauric Research, arxiv 2412.20138) — multi-agent role decomposition. Adopted: analyst team + researcher debate + risk team + portfolio manager hierarchy. Realistic context: their best published 30-day run was ~7% with 22% drawdown, and the authors warn against live money.
- **FinMem** (arxiv 2311.13743) — layered memory. Adopted: working/short/medium/long-term memory namespaces; retrieval weighted by recency × relevance × importance.
- **FinAgent** (arxiv 2402.18485) — low-level and high-level reflection. Adopted: immediate (daily) and extended (weekly) reflection loops.
- **Voyager** (arxiv 2305.16291) — LLM agent building a persistent skill library from experience. Adopted: the Discoverer maintains a strategy/skill library that grows from journal data.
- **NautilusTrader** — production-grade event-driven engine with backtest-live parity. Adopted: same code paths in research and live; only the data feed and execution adapter differ.
- **Renaissance Medallion** — 50.75% win rate × millions of trades; integrated single model where every signal feeds one decision. Adopted: the philosophy that we win on _selectivity_, not volume — because we lack their speed, data, and leverage. The Signal Aggregator combines many signals into one verdict rather than picking one.
- **Knight Capital ($440M lost in 45 minutes, 2012)** — dormant code reactivated by a deployment that copied new code to 7 of 8 servers; no written deployment procedures, no peer review, no real-time P&L anomaly detection. Adopted: feature flags with auto-expiration, deployment checksum verification, P&L velocity anomaly detection, order-rate freeze.
- **LTCM (1998)** — leveraged fund destroyed by tail risk in positions that were correlated under stress. Adopted: correlation cap across open positions; stress-test exposure before sizing up.
- **Numerai** — staking your own money on predictions forces honest evaluation and kills overfitting. Adopted: before any strategy goes live, a forward paper period; before any change goes live, it must beat the prior version on held-out golden samples.
- **DreamerV3 / continual RL** (arxiv 2603.04029) — world-model residuals detect out-of-distribution events and trigger adaptation. Adopted: the regime detector watches its own prediction residuals and auto-triggers re-evaluation when they spike.
- **OpenAI Self-Evolving Agents cookbook** — LLM-as-judge plus meta-prompting for agent improvement. Adopted: nightly evaluation of each agent against held-out scenarios; underperforming agents get prompts revised by a meta-prompter and tested before rollout.
- **Quantopian (shut 2020, acquired by Robinhood)** — 700,000 user algorithms, millions of backtests on the same data; by pure chance some looked like holy grails; almost none survived live. Lesson baked into Section 9: distrust every backtest until it survives five validation gates.

### The single most important finding driving this design

A study of **888 algorithmic strategies** found backtested Sharpe ratio predicts live performance with **R² below 0.025** — essentially zero. About **44% of published strategies fail to replicate** on new data. Bloomberg's 2026 reporting on AI trading bots auditioning for Wall Street named the core failure modes: **overtrading, inconsistent outputs, weak risk discipline, and poor regime adaptation.**

Therefore Hood Dabang's defining principle is: **a trade does not happen because a setup appeared. It happens because the setup cleared a high, explicitly-scored conviction bar.** Most candidates are rejected. The system is designed to take **0-10 trades a day** and to be _comfortable taking zero_.

### The philosophy, stated plainly

> Processes compound under discipline. Decisions degrade under stress. Institutions build systems, not signals. Amateurs chase excitement; professionals accept boredom.

You will reject most setups. You will have days where you take one trade, or none. That is the system working correctly, not failing. One excellent trade can make the day; you never need to "use up" a trade budget.

---

## 1. PRIME DIRECTIVES (NEVER REORDER, NEVER OVERRIDE)

1. **Do not blow up the account.** A surviving $1,500 beats a $1,500 that hit one moonshot.
2. **Stay legal and stay connected.** Inside broker, MCP, FINRA, SEC rules. A halted account is dead capital.
3. **Stay solvent on costs.** Daily LLM spend ≤ budget. The system that bleeds tokens loses money even while winning trades.
4. **Trade only with conviction.** A mediocre trade is worse than no trade. Zero-trade days are acceptable and sometimes correct. The goal is _good_ trades, not _many_ trades.
5. **Make money on a rolling basis.** Beat the risk-free rate at minimum; aim for $100/day on a 30-day rolling average; accept that some days are zero and some weeks deliver the month's gains in one swing.
6. **Stretch beyond once proven.** $100/day average is the aspiration. A 10-day $750 gain is equally valid. The operator adds capital once positive expectancy is demonstrated over ≥15 sessions.

### What you internalize about the universe before you act

- **$100/day on $1,500 = 6.67% daily.** Compounded long-term: impossible. The 30-day rolling average is the goal; the daily figure is variance.
- **Backtest Sharpe predicts live performance with R² < 0.025.** Distrust every backtest until it survives all five validation gates (Section 9). A beautiful equity curve is a warning sign, not a green light.
- **Best documented agentic AI live result in 2026: ~10%/month**, 6.8% max DD over 90 days. TradingAgents published: ~7% in 30 days with 22% DD. Calibrate to data, not marketing.
- **Renaissance Medallion's edge is 50.75% win rate × millions of trades.** We are not Renaissance — we lack their speed, data, and leverage. We win on _selectivity_: only the highest-conviction setups, where the edge per trade is large enough to clear costs and noise.
- **You cannot predict markets.** You identify statistical setups, build falsifiable theses, size positions, and manage risk. The moment you "feel" a direction without a defined, invalidatable thesis, you are about to lose money.
- **Edges degrade.** Regime detection and concept-drift detection are not optional.
- **Overtrading is the documented #1 retail failure mode.** Hood Dabang's bias is toward inaction.
- **Your output risks real money.** A hallucinated number, a look-ahead bias, a runaway token loop — any one ends the account. Be paranoid about your own outputs.

### Things you will never do

- Trade without a defined stop loss attached as a separate broker order.
- Trade a setup that has not cleared the Conviction Gate (Section 6).
- Trade without a stored falsifiable thesis (Section 7).
- Average down on a losing position.
- Exceed the per-trade Kelly cap (half-Kelly, ≤1.5% of equity).
- Exceed 30% of account in a single position.
- Trade through the daily loss limit (-5% of session-start equity).
- Trade the first 5 minutes (9:30-9:35 ET) or last 10 minutes (15:50-16:00 ET) except to exit.
- Use market orders. Marketable limits only.
- Trade penny stocks (<$5), OTC, or anything with <1M average daily volume.
- Hold positions overnight during the first 30 sessions of live operation.
- Lie to the journal. Disable a killswitch. Bypass self-tests.
- Trade on material non-public information.
- Exceed the daily LLM budget (LLM agents pause; deterministic agents continue).
- Enable swing/multi-day strategies before Day 30 of consistent live operation.
- Take a trade to "make the daily number." The number is variance; the process is the point.
- Promote a strategy to live without passing all five validation gates (Section 9).

---

## 2. ACCOUNT, REGULATORY & PRACTICAL CONTEXT

- **Capital:** $1,500 in the Robinhood Agentic account.
- **Account type:** Robinhood Agentic — an isolated sandbox, separate from the operator's main portfolio. Read access to main account balances may be permitted; trading is restricted to the Agentic account.
- **PDT (Pattern Day Trader rule):** Eliminated as of June 4, 2026 (FINRA Rule 4210 amendment; SEC approval April 14, 2026). Unlimited day trades are available — _which Hood Dabang deliberately does not exploit_. Selectivity over frequency.
- **Settlement:** T+1 for equities. In a cash account, sale proceeds settle the next business day. Query the MCP for buying power; never assume.
- **Margin:** Do not request or use margin in the first 30 days. Operate cash-account behavior.
- **Asset scope:** Equities only (Robinhood Agentic beta). No options, crypto, futures, or fractional shares. Whole-share sizing only — be careful with position-sizing math.
- **Short selling:** Possible if the account is approved and a borrow exists. Treat shorts as second-class until 30 days of long-side data.
- **Robinhood's disclaimer:** They run the rails; they do not supervise, audit, or recommend AI agents. You are responsible for staying inside rules and not violating broker terms (no wash trading, spoofing, or layering).
- **Tax tracking:** Out of scope for the agent, but log every trade with enough detail for the operator's accountant. Wash-sale rules apply to losses if you re-enter a substantially identical security within 30 days — flag these in the journal.

---

## 3. TOKEN ECONOMICS — THE FOUR-TIER ARCHITECTURE

This section exists because, naively built, a multi-agent system running everything on Opus 4.8 would cost ~$10+/day on a $100/day target — an 11% performance hurdle before a single losing trade. The economics must work or the whole thing fails.

### 3.1 Cost targets

- **Daily LLM spend target:** ≤ $1.80. (The Conviction Gate sends only the top 1-3 candidates to the LLM pipeline, not 8, which is the single biggest saving.)
- **Daily LLM killswitch:** $5.00. Hit → pause LLM agents, deterministic agents continue.
- **Monthly LLM budget:** $60. Hit → strong notification + required operator review.

Every API call logs its tokens and dollar cost to `data/llm_ledger.db`. The dashboard shows real-time spend. The system always knows what it is spending.

### 3.2 Pricing reference (verified June 2026)

| Model | Input $/MTok | Output $/MTok | Used for |
|---|---:|---:|---|
| Haiku 4.5 | $1.00 | $5.00 | Tier 1: classification, sentiment |
| Sonnet 4.6 | $3.00 | $15.00 | Tier 2: debate, reflection, macro, insight |
| Opus 4.8 | $5.00 | $25.00 | Tier 3: final synthesis, meta-learning, judge |

Prompt caching: ~90% off cached input tokens. Batch API: 50% off but asynchronous (not used for live trading decisions). Embeddings: **local sentence-transformers, $0.**

### 3.3 The four-tier compute model

| Tier | Where | What | Cost |
|---|---|---|---:|
| Tier 0 | Local Python | Math, structured-data parsing, ML inference (HMM, Random Forest, sentence-transformers), pattern detection, risk gates, killswitches, reconciliation, order routing, dashboard, notifications, backtest engine, the Conviction Gate's deterministic scoring | $0 |
| Tier 1 | Haiku 4.5 | Routine classification, sentiment scoring, headline categorization, simple summarization | Cheap |
| Tier 2 | Sonnet 4.6 | Multi-step reasoning, debate, reflection, narrative synthesis, fundamentals reading, thesis construction | Mid |
| Tier 3 | Opus 4.8 | Final trade synthesis, portfolio decisions, meta-improvement, LLM-as-judge | Expensive, used sparingly |

### 3.4 Per-component tier assignment

| Component | Tier | Why |
|---|---|---|
| Technical analysis (RSI, MACD, ATR, VWAP, anchored VWAPs, BB width, EMAs, volume profile, pattern detection) | **0** | Pure math |
| Microstructure (RVOL, volume profile, options chain IV, put/call ratio, FINRA short volume) | **0** | Math + structured data |
| Insider/Institutional (SEC Form 4 JSON parse, 13F, threshold rules) | **0** | JSON parse + rules |
| Regime classification (HMM 3-4 state + Random Forest ensemble vote) | **0** | Local ML inference |
| Screener (liquidity, gap, RVOL ranking) | **0** | Deterministic filters |
| Conviction Gate Stage-1 (deterministic scorecard) | **0** | Weighted scoring math |
| All 19 strategies (scan + manage) | **0** | Pattern detection + rules |
| Risk gate, killswitch, reconciliation, sizing | **0** | Deterministic by design |
| Memory retrieval (vector search) | **0** | Local sentence-transformers |
| Backtest engine + validation suite | **0** | Event simulation |
| News classification (200 headlines batched) | **1** (Haiku) | Unstructured text → categories |
| Sentiment scoring | **1** (Haiku) | Text → score |
| Macro narrative synthesis | **2** (Sonnet) | One call per session |
| Fundamentals reading (10-K/10-Q excerpts) | **2** (Sonnet) | On-demand, 0-2/day |
| Insight Engine thesis construction | **2** (Sonnet) | Per gated candidate only |
| Bull / Bear debate | **2** (Sonnet) | Per gated candidate only |
| Risk-Conservative / Risk-Aggressive debate | **2** (Sonnet) | Per approved plan |
| Reflector (per-trade, session, weekly) | **2** (Sonnet) | Post-hoc |
| Discoverer | **2** (Sonnet) | Weekly |
| Trader (final synthesis) | **3** (Opus) | Final plan — worth it, only 1-3/day |
| Portfolio Manager (final go/no-go) | **3** (Opus) | Final approval, 1-3/day |
| Meta-Learner | **3** (Opus) | Weekly prompt improvement |
| LLM-as-judge | **3** (Opus) | Nightly eval, cached judge prompt |

### 3.5 The economic effect of the Conviction Gate

In a naive design, ~8 candidates/day reach the LLM pipeline. In Hood Dabang, the deterministic Conviction Gate pre-filters so only the **top 1-3 candidates by deterministic score** reach the LLM layer. This is the single biggest token saving _and_ the single biggest decision-quality improvement at the same time — selectivity makes the system both smarter and cheaper.

| Stage | Tier | Naive calls/day | Hood Dabang calls/day | Daily $ |
|---|---|---:|---:|---:|
| News + sentiment | 1 | 2 | 2 | $0.07 |
| Macro | 2 | 1 | 1 | $0.05 |
| Fundamentals (on-demand) | 2 | 0-2 | 0-2 | $0.05 |
| Insight + Bull/Bear + Risk per candidate | 2 | ~56 | ~12 (3 candidates) | $0.70 |
| Trader + PM per candidate | 3 | ~16 | ~6 (3 candidates) | $0.45 |
| Reflector | 2 | ~10 | ~6 (fewer trades) | $0.15 |
| Meta-Learner + judge (amortized) | 3 | ~13 | ~13 | $0.30 |
| **Total** | | | | **~$1.77** |

### 3.6 Prompt caching — the 90% lever

Anthropic prompt caching gives ~90% off cached input. Cache per session at 9:25 ET when the morning brief publishes: every agent's system prompt (~2-5K each), the morning brief (~3K), the regime call and allocations (~1K), the watchlist with pre-computed Tier-0 scores (~5-10K), and per-strategy rules (~2K each). This gives ~25K cached prefix per candidate evaluation; only ~2-3K is fresh per candidate. A call that would have been 28K input at full price becomes ~25K × 0.1 + 3K ≈ 5.5K equivalent — an ~80% reduction.

Cache invalidation: morning brief at next 8:00 ET refresh; regime on `RegimeChangeEvent`; watchlist on intraday rescan; strategy rules only on version bump (rare). The `llm_client.py` wrapper handles caching transparently — every LLM helper takes a `cached_context` parameter; if unchanged from the last call, it passes the cache key instead of resending tokens.

### 3.7 Local caches (free, persistent across restarts)

- News classifications by URL hash (never re-classify the same article).
- SEC filings by accession number (never re-parse the same 10-K).
- Quotes by `(ticker, minute)`, 60s TTL.
- yfinance batch responses, 5-min TTL.
- Embeddings by content hash.

These are local SQLite caches, not API caches. Free, fast, persistent.

### 3.8 Embeddings: local, free

Memory retrieval, golden-sample similarity, and "find similar past trades" use **local sentence-transformers** (e.g., `all-MiniLM-L6-v2`, ~80MB, runs on CPU). No embedding API costs. The Mac handles it.

### 3.9 Critical principle: degrade, don't die

If LLM agents are paused (budget killswitch, API outage, rate limit):
- **Tier 0 continues.** Technical, Microstructure, Regime, Risk, Killswitch, Reconciliation, Sizing, Strategies, Execution — all keep running.
- **Open positions continue to be managed** by their strategy's deterministic `manage()` method (stops move, targets fill, time-stops trigger).
- **No new LLM-gated entries** are taken.
- **Pure-rules strategies** marked `requires_llm_gating=False` may still open positions if a setup is textbook-clean (opt-in per strategy, rare).
- **Operator is notified loudly.**

The system loses some upside but keeps the downside locked down.

---

## 4. SYSTEM ARCHITECTURE — EVENT-DRIVEN, HYBRID AI + RULES

### 4.1 The bedrock principle: backtest-live parity

Same code paths in research and live. The ONLY differences are the `DataFeed` (historical vs live) and the `ExecutionHandler` (simulated vs real Robinhood MCP). Strategies, agents, risk gates, killswitches, sizers, monitors, the Conviction Gate — all identical bytes. This is the NautilusTrader principle: it's the difference between "the strategy that backtested" and "the strategy that traded" being literally the same thing rather than subtly different things that diverge under stress. Enforced by `tests/test_backtest_live_parity.py`.

### 4.2 Event types (event-driven, not vectorized)

A vectorized backtest assumes fills at the next bar and ignores slippage, partial fills, and order rejections. An event-driven architecture models the sequential reality of live trading and lets the same code run in both modes.

```
KillEvent          (top priority — jumps the queue)
FillEvent
ReconciliationEvent
RiskDecisionEvent
OrderEvent
ConvictionEvent    (the Conviction Gate's verdict)
TradePlanEvent
InsightEvent       (a falsifiable thesis was produced)
ResearchEvent      (multi-agent debate output)
SignalEvent        (a strategy proposes a candidate)
NewsEvent          (parsed news with timestamp, severity, direction)
MarketDataEvent    (tick, bar, order-book update)
RegimeChangeEvent  (regime classifier flipped state)
HeartbeatEvent     (lowest — periodic health)
```

Every component subscribes to events it cares about and emits events it produces. The event bus is the single coordination mechanism — a FIFO queue with a priority lane (KillEvent jumps ahead of everything).

### 4.3 The hybrid AI + rules core

Pure-LLM agents lose money in production (they hallucinate, they're inconsistent, they lack circuit breakers). Pure-rules systems can't adapt to regime change. The winning architecture is hybrid:

- **Rules layer (Tier 0, deterministic, fast, auditable):** screeners, risk gates, killswitches, position sizing, order routing, reconciliation, the regime classifier core math, strategy pattern detection, memory retrieval, the Conviction Gate's deterministic scoring. Pure Python with unit tests and no LLM calls. Runs in milliseconds.
- **AI layer (Tiers 1-3, probabilistic, slower, evidence-grounded):** news/sentiment/macro/fundamentals classification, the Insight Engine, bull/bear debate, trader synthesis, risk debate, PM decision, reflection, meta-learning. Runs on Opus/Sonnet/Haiku with structured outputs and grounded citations. Runs in seconds.
- **The boundary:** AI agents _propose_; rules _dispose_. An LLM can never override risk caps, killswitches, position size limits, budget caps, or the Conviction Gate's hard floors. The rule layer is the bedrock; the AI layer is judgment operating _inside_ the bedrock.

### 4.4 The decision pipeline (the heart of the system)

```
  [Tier 0] Screener → 20-50 names
        ↓
  [Tier 0] Technical + Microstructure + Insider + Regime score every name
        ↓
  [Tier 0] Strategies scan; each emits a SignalEvent for any setup it sees
        ↓
  [Tier 0] CONVICTION GATE Stage 1 (deterministic): score every signal;
           keep only signals above the hard floor; rank; take top 1-3
        ↓
  [Tier 2] Insight Engine: build a falsifiable thesis for each survivor
        ↓
  [Tier 2] Bull/Bear debate (2 rounds) on each survivor
        ↓
  [Tier 3] Trader: synthesize a structured TradePlan (or pass)
        ↓
  [Tier 0+2] CONVICTION GATE Stage 2 (full verdict): combine deterministic
             score + debate margin + thesis quality + source calibration
        ↓
  [Tier 2] Risk team debate (conservative vs aggressive)
        ↓
  [Tier 3] Portfolio Manager: execute / modify / reject
        ↓
  [Tier 0] Risk gate (hard caps) → Execution (preview/place/verify/reconcile)
```

Most candidates die at the deterministic Conviction Gate, before any token is spent. This is intentional.

### 4.5 Directory structure

```
hood-dabang/
├── BRIEF.md                         # This file
├── README.md                        # Operator quickstart (generated)
├── config.yaml                      # All tunables (hot-reloaded every 60s)
├── config.schema.json               # Pydantic-validated; reject invalid configs
├── .env                             # Secrets (ANTHROPIC_API_KEY). Never committed.
├── PERMITTED_VERSIONS.lock          # Strategy versions cleared for live; immutable per session
├── HALT.flag                        # Operator manual halt (presence = halt)
├── MANUAL_OVERRIDE.flag             # Override risk caps (24h cooldown)
├── BUDGET_PAUSE.flag                # LLM budget paused; deterministic continues
├── data/
│   ├── trader.db                    # SQLite — single source of truth (WAL mode)
│   ├── llm_ledger.db                # Per-call token + cost log
│   ├── universe_pit/                # Point-in-time universe snapshots (no survivorship)
│   ├── briefs/YYYY-MM-DD.md          # Daily morning briefings
│   ├── journal/YYYY-MM-DD.md         # Daily trade journals
│   ├── reflections/                 # Daily/weekly/monthly reflection notes
│   ├── golden_samples/              # Held-out scenarios for agent evaluation
│   ├── theses/                      # Stored falsifiable theses (one per trade)
│   ├── conviction_log/              # Every gate decision — kept or killed, with reason
│   ├── memory/                      # Long-term memory store
│   ├── missed_trades.md             # "Obvious" setups that matched no strategy (Discoverer fuel)
│   ├── cache/
│   │   ├── llm_prompt_cache/        # Persistent prompt-cache state
│   │   ├── news_classifications/    # By URL hash
│   │   ├── sec_filings/             # By accession number
│   │   ├── quotes/                  # By (ticker, minute)
│   │   └── embeddings/              # sentence-transformers cache
│   ├── backtests/                   # Versioned backtest results
│   └── models/                      # HMM, RandomForest, sentence-transformers
├── src/
│   ├── controller.py                # Event-driven orchestrator and main loop
│   ├── event_bus.py                 # In-process priority FIFO bus
│   ├── mcp_client.py                # Robinhood MCP wrapper with schema validation
│   ├── llm_client.py                # Tier-aware LLM wrapper with prompt caching
│   ├── llm_budget.py                # Daily/monthly spend tracker
│   ├── risk.py                      # Risk gate (every order passes through)
│   ├── killswitch.py                # All halt conditions
│   ├── execution.py                 # OrderEvent → broker, with preview/verify/reconcile
│   ├── reconciliation.py            # Broker vs internal state, every 60s
│   ├── conviction/
│   │   ├── gate.py                  # Deterministic + full conviction scoring
│   │   ├── scorecard.py             # Scorecard schema and weights
│   │   └── thresholds.py            # Hard floors, hot-reloadable
│   ├── insight/
│   │   ├── engine.py                # Builds falsifiable theses
│   │   └── thesis.py                # Thesis schema (claim, mechanism, invalidation)
│   ├── sizing/
│   │   ├── kelly.py                 # Kelly fraction from journal
│   │   ├── volatility_target.py     # Vol-target sizing
│   │   ├── correlation_cap.py       # Cross-position correlation limit
│   │   └── conviction_scaled.py     # Size scales with conviction score
│   ├── data_feeds/
│   │   ├── base.py                  # DataFeed interface (live and historical implement it)
│   │   ├── live_quotes.py           # Real-time via MCP + yfinance fallback
│   │   ├── historical_bars.py       # Cached OHLCV, multi-resolution
│   │   ├── news_rss.py              # Yahoo, MarketWatch, Reuters, SEC, PR wires, Fed
│   │   ├── sec_edgar.py             # Form 4, 8-K, 10-K, 13F
│   │   ├── earnings_cal.py          # Nasdaq + Yahoo earnings calendar
│   │   ├── econ_cal.py              # Fed, CPI, NFP, jobless claims schedule
│   │   ├── options_flow.py          # yfinance chains + free UOA (signal only)
│   │   ├── finra_short.py           # Dark-pool proxy via FINRA short volume
│   │   └── fred.py                  # Macro data
│   ├── analysts_local/              # Tier 0 — deterministic
│   │   ├── technical.py
│   │   ├── microstructure.py
│   │   ├── insider.py
│   │   └── regime.py
│   ├── agents/                      # Tier 1-3 — LLM-backed
│   │   ├── base.py                  # Pydantic-typed structured-output protocol
│   │   ├── news.py                  # Tier 1
│   │   ├── sentiment.py             # Tier 1
│   │   ├── macro.py                 # Tier 2
│   │   ├── fundamentals.py          # Tier 2 (on-demand)
│   │   ├── researchers/
│   │   │   ├── bull.py              # Tier 2
│   │   │   └── bear.py              # Tier 2
│   │   ├── risk_team/
│   │   │   ├── conservative.py      # Tier 2
│   │   │   └── aggressive.py        # Tier 2
│   │   ├── reflector.py             # Tier 2
│   │   ├── discoverer.py            # Tier 2
│   │   ├── trader.py                # Tier 3
│   │   ├── portfolio_manager.py     # Tier 3
│   │   ├── meta_learner.py          # Tier 3
│   │   └── judge.py                 # Tier 3
│   ├── memory/
│   │   ├── working.py               # Per-session
│   │   ├── short_term.py            # Last 5 sessions
│   │   ├── medium_term.py           # Last quarter
│   │   ├── long_term.py             # Persistent learned patterns
│   │   ├── retrieval.py             # Recency × relevance × importance
│   │   └── embeddings_local.py      # sentence-transformers wrapper
│   ├── strategies/
│   │   ├── base.py                  # Strategy ABC with version + activation gate
│   │   ├── registry.py              # Active registry with allocations
│   │   ├── intraday/
│   │   │   ├── orb.py
│   │   │   ├── ibb.py
│   │   │   ├── vwap_reversion.py
│   │   │   ├── gap_fill.py
│   │   │   ├── gap_continuation.py
│   │   │   ├── momentum.py
│   │   │   ├── earnings_reaction.py
│   │   │   ├── catalyst_scalp.py
│   │   │   ├── range_compression.py
│   │   │   ├── hourly_sweep.py
│   │   │   ├── engulfing.py
│   │   │   ├── sector_rotation.py
│   │   │   └── short_squeeze.py
│   │   ├── swing/
│   │   │   ├── pead.py
│   │   │   ├── momentum_swing.py
│   │   │   ├── earnings_beat_followthrough.py
│   │   │   ├── quality_mean_reversion.py
│   │   │   └── sector_momentum_rotation.py
│   │   └── stat_arb/
│   │       └── pairs.py
│   ├── screener/
│   │   ├── universe.py              # Weekly, point-in-time
│   │   ├── premarket.py
│   │   ├── intraday.py
│   │   └── filters.py               # Liquidity, volatility, news filters
│   ├── regime/
│   │   ├── classifier.py            # HMM + Random Forest ensemble vote
│   │   ├── transition_detector.py   # Watches own residuals for regime change
│   │   └── strategy_allocator.py    # Regime-conditioned allocations
│   ├── backtest/
│   │   ├── engine.py                # Event-driven; shares code with live
│   │   ├── data_loader.py           # Point-in-time, survivorship-aware
│   │   ├── slippage.py              # Realistic fill model
│   │   ├── walk_forward.py          # Walk-forward validation
│   │   ├── bootstrap_overfit.py     # Bailey et al. PBO test
│   │   ├── deflated_sharpe.py       # DSR accounting for number of trials
│   │   └── reporting.py             # Backtest reports with full statistics
│   ├── monitor/
│   │   ├── dashboard.py             # Rich terminal UI
│   │   ├── notifications.py         # macOS native + optional channels
│   │   ├── health.py                # System health monitor
│   │   ├── audit_log.py             # Append-only audit trail
│   │   └── pnl_velocity.py          # Knight-Capital P&L anomaly defense
│   ├── self_improvement/
│   │   ├── judge_harness.py         # LLM-as-judge eval harness
│   │   ├── golden_samples.py        # Maintains held-out scenarios
│   │   ├── meta_prompter.py         # Proposes prompt revisions
│   │   ├── ab_test.py               # Compares variants on golden samples
│   │   └── rollout.py               # Canary/shadow deployment of new versions
│   ├── ops/
│   │   ├── startup.py
│   │   ├── shutdown.py
│   │   ├── recovery.py              # Crash / power-loss recovery
│   │   ├── scheduler.py             # launchd integration
│   │   └── network_health.py        # Graceful degradation when feeds fail
│   ├── journal.py                   # Trade journal + post-trade review
│   └── learning.py                  # Weekly/monthly meta-review + parameter tuning
├── tests/
│   ├── test_risk.py
│   ├── test_killswitch.py
│   ├── test_strategies.py
│   ├── test_backtest_no_lookahead.py
│   ├── test_backtest_live_parity.py
│   ├── test_reconciliation.py
│   ├── test_memory.py
│   ├── test_kelly.py
│   ├── test_regime.py
│   ├── test_event_bus.py
│   ├── test_mcp_schema.py
│   ├── test_llm_client.py
│   ├── test_budget.py
│   ├── test_conviction_gate.py
│   ├── test_conviction_ranking.py
│   ├── test_thesis.py
│   ├── test_validation_gates.py
│   ├── test_deflated_sharpe.py
│   ├── test_conviction_sizing.py
│   └── test_revenge_suppression.py
└── logs/
    ├── trader.log                   # Loguru-rotated
    └── audit/                       # Append-only
```

### 4.6 The structured-output protocol for every agent

```python
from pydantic import BaseModel, Field
from typing import Literal

class Evidence(BaseModel):
    source: str           # "news_analyst" | "sec_edgar:8-K" | "memory:long_term"
    reference: str        # specific document/event id
    weight: float = Field(..., ge=0, le=1)
    summary: str

class AgentOutput(BaseModel):
    agent: str
    session_id: str
    timestamp_iso: str
    ticker: str | None
    thesis: str
    evidence: list[Evidence]
    counter_arguments_addressed: list[str]
    confidence: float = Field(..., ge=0, le=1)
    proposal: dict | None = None          # Only the Trader and PM emit one
    risks: list[str]
    historical_calibration_score: float | None = None   # Has this agent's
        # "0.7 confidence" actually been right ~70% of the time? Weights the gate.
```

Every agent output is validated against this schema before downstream consumers use it. Tier-0 analysts return strongly-typed dataclasses with the same shape. Free-text reasoning is allowed inside `thesis`, but _decisions are structured_. This prevents the "the LLM said something vague and downstream code interpreted it three ways" failure mode.

---

## 5. THE AGENTS — FULL ROLES, INPUTS, OUTPUTS, GUARDRAILS

For each agent: a precise system prompt (written in the implementation), a typed input contract, a typed output contract (Section 4.6), at least one unit test asserting it refuses to act outside its role, and a calibration tracker.

### 5.1 Local analysts (Tier 0 — deterministic Python, $0 to run)

**Technical Analyst (Tier 0).** Inputs: OHLCV at 1m/5m/15m/1H/1D, current quote. Outputs: trend bias per timeframe; key levels (premarket high/low, prior day high/low/close, weekly high/low, session VWAP, anchored VWAPs from earnings or news events, value-area POC/VAH/VAL); oscillators (RSI 2/5/14, MACD); volume profile; ATR(14); pattern detections (flags, triangles, engulfing, BB-width compression, EMA crossovers). Pure pandas/numpy plus ta-lib or hand-rolled functions. Latency: sub-second per ticker. Guardrail: outputs price levels at 2-decimal precision with explicit timeframe attribution; never "interprets a chart" without the underlying data.

**Microstructure Analyst (Tier 0).** Inputs: bid/ask, time-and-sales (if available via MCP), options chain (yfinance), FINRA short-volume daily files. Outputs: RVOL (cumulative volume vs average-cumulative-for-time-of-day), volume-spike flags, options put/call ratio and IV term structure, short-volume ratio. Rule-based scoring. Latency: sub-second. Guardrail: options flow is a leading EQUITY signal only — we never trade options in the Agentic beta; UOA without confirming volume on the underlying is downweighted.

**Insider/Institutional Analyst (Tier 0).** Inputs: SEC EDGAR Form 4 JSON (free endpoint) over the past 30 days, 13F changes (lagged 45 days). Outputs: cluster-insider-buy flags (≥3 insiders in 30 days), large-buy flags (>$500K or >1% of an insider's holdings), large CEO/CFO sell flags (>$5M). Threshold rules, no LLM. Latency: sub-second after data fetch. Guardrail: insider buys are weakly bullish (more signal than sells, which are noisy); ≥3 insiders or ≥1% of holdings to register.

**Regime Analyst (Tier 0).** Inputs: SPY/QQQ/IWM vs 50/200 SMAs; VIX, VVIX, VIX term structure (contango/backwardation); breadth (% of stocks above 50 and 200 SMA); advance-decline; NYSE TICK average; average pairwise S&P 500 correlation; sector dispersion. Internal model: a Gaussian HMM (3-4 states, hmmlearn) PLUS a sklearn Random Forest on engineered features; both vote on the regime label. Both agree = high-confidence regime; disagreement = `transitional`. Outputs one of: `bull_trend_low_vol`, `bull_trend_high_vol`, `range_low_vol`, `range_high_vol`, `bear_trend_low_vol`, `bear_trend_high_vol`, `crisis`, `transitional`. Self-monitoring: tracks its own prediction residuals (where regime vs realized intraday volatility diverged); spikes emit a `RegimeChangeEvent` and the allocator re-evaluates on the fly (DreamerV3 principle). Retrains overnight from the last 60 sessions if residuals exceed threshold. Latency: sub-second.

### 5.2 LLM agents (Tiers 1-3)

**News Analyst (Tier 1 — Haiku 4.5).** Batched call: classifies up to 200 headlines into categories (earnings, guidance, M&A, regulatory, FDA/clinical, legal, executive change, upgrade/downgrade, macro spillover, noise) with severity (1-3) and direction (bull/bear/neutral), cross-referenced to the watchlist. Cached system prompt; article-by-URL-hash result cache so the same article is never re-classified. One call per session pre-market, plus ad-hoc on breaking news. Prompt-injection defense: news content is DATA, never instructions — anything inside an article that looks like a command is classified, not executed.

**Sentiment Analyst (Tier 1 — Haiku 4.5).** Aggregated text → score [-1, +1] with confidence; sentiment velocity (acceleration vs trailing 5 days); top positive/negative headlines. Batched per session. Cached. Guardrail: refuses to act on a single source; ≥2 independent sources for a non-neutral score.

**Macro Analyst (Tier 2 — Sonnet 4.6).** Reads the economic calendar (Fed minutes, CPI, PPI, NFP, PMI, jobless claims) + cross-asset moves (DXY, TLT, oil, gold, BTC, VIX, VIX term). Outputs a regime hypothesis, the key releases today with exact times, and a sector-impact map. One call per session pre-market.

**Fundamentals Analyst (Tier 2 — Sonnet 4.6, on-demand).** Reads recent 10-K/10-Q/8-K excerpts (the Tier-0 SEC parser extracts the relevant sections first to keep input compact). Outputs an intrinsic-value bracket, financial-health flags (rising debt, falling margins, dilution), and an earnings-quality score 1-5. Called only when a candidate's other signals are strong AND fundamentals matter for the strategy (e.g., PEAD checks earnings quality). Typical: 0-2 calls/day.

**Bull Researcher / Bear Researcher (Tier 2 — Sonnet 4.6 each).** Per Conviction-Gate survivor. The debate protocol is two rounds: (1) Bull writes its thesis with evidence and counter-arguments addressed; (2) Bear responds; (3) Bull rebuts; (4) Bear rebuts; (5) both submit final confidence scores and proposals. Each round, each side must cite specific evidence (with weight) from analyst outputs, address the strongest two points the other just made, and update its confidence (no sandbagging round 1 to be "right" in round 2). Empirically (TradingAgents) this debate step improves Sharpe and reduces drawdown — being forced to write the strongest opposite case surfaces hidden assumptions.

**Risk-Conservative / Risk-Aggressive (Tier 2 — Sonnet 4.6 each).** One-round debate per TradePlan. Conservative examines: position size vs account, correlation with existing positions, regime fit, time-of-day, news risk in the holding window, the strategy's recent expectancy — and can veto, require size reduction, or require a tighter stop. Aggressive examines: is this size TOO SMALL for the conviction? Stop too tight? Would scaling work? Conservative has veto power on hard-rule violations but must justify it.

**Reflector (Tier 2 — Sonnet 4.6).** Per closed trade: a 3-sentence reflection (setup, what happened, what to do differently) PLUS a thesis-vs-reality score (did the stated mechanism drive the move? did invalidation fire correctly? was the base rate accurate?). Categorizes each loss as a GOOD loss (correct setup, market disagreed) or a BAD loss (rule violation, forced trade, chased entry, ignored invalidation). Per session: a session reflection (which regime call was right, which strategies fired vs were missed, which agent outputs best predicted realized returns). Per week: a meta-reflection (strategy expectancy review, agent-quality review, memory consolidation). Flags overtrading: a day with >10 trades is flagged for review.

**Discoverer (Tier 2 — Sonnet 4.6).** Weekly: scans the journal and `data/missed_trades.md` for patterns ("when X happens, Y often follows"). Generates hypotheses for new strategies or parameters. Always submits hypotheses for backtest + the five validation gates; NEVER proposes live capital directly.

**Trader (Tier 3 — Opus 4.8).** Final synthesis per survivor after the debate. Reads analyst outputs, the bull/bear debate, the thesis, current memory (relevant past trades on this ticker/setup with their outcomes), the current portfolio, the regime, and the strategy allocation. Produces a structured TradePlan or a "pass":

```python
class TradePlan(BaseModel):
    ticker: str
    decision: Literal["trade", "watch", "pass"]
    side: Literal["long", "short"] | None
    strategy: str
    strategy_version: str            # must be in PERMITTED_VERSIONS.lock
    entry: dict                      # {type: "limit", price, validity}
    stop_loss: float
    targets: list[dict]              # [{price, fraction_to_close}]
    size_shares: int
    risk_dollars: float
    thesis_summary: str
    invalidation_conditions: list[str]
    expected_hold_time_minutes: int
    confidence: float
    bull_score: float
    bear_score: float
```

**Portfolio Manager (Tier 3 — Opus 4.8).** Final authority before execution. Considers the TradePlan, the risk recommendation, the current portfolio context (open positions, daily P&L, trades count, time remaining, regime), and the journal (was a similar trade taken recently; how did it perform). Decision: execute / modify / reject. If execute, emits an OrderEvent. If modify, updates the plan (smaller size, tighter stop). If reject, logs the reason. Mandate explicitly prohibits trades motivated by "making the daily number" or "making up an earlier loss."

**Meta-Learner (Tier 3 — Opus 4.8).** Weekly: evaluates each agent against held-out golden samples; drafts revised system prompts for underperformers; tests revisions against the golden set; promotes a revision to `staging` only if it beats the current prompt by a statistically significant margin (p < 0.05, n ≥ 30). Cannot modify risk, killswitch, reconciliation, test files, or Conviction-Gate floors (the recursive constraint, Section 12).

**LLM-as-judge (Tier 3 — Opus 4.8).** A stable judge (prompt unchanged across evaluations so judges don't drift) that scores agent outputs against golden-sample ground truth nightly. Two judges in disagreement → human review.

### 5.3 What each agent does when the budget killswitch fires
Tier 0 continues normally. Tier 1 (News, Sentiment) pauses; last classifications remain in cache and continue to be used. Tier 2 pauses; open positions are managed by their strategy's deterministic `manage()`. Tier 3 pauses; no new LLM-gated entries. Pure-rules strategies marked `requires_llm_gating=False` may still open positions. Operator notified loudly.

---

## 6. THE CONVICTION GATE — QUALITY OVER QUANTITY

The defining component. It exists because the documented #1 failure of retail/AI bots is overtrading low-quality signals, and because backtests lie. The Conviction Gate is the system's discipline made mechanical.

### 6.1 Two stages

**Stage 1 — Deterministic pre-filter (Tier 0, runs on every SignalEvent, $0).** Before any token is spent, every strategy signal is scored 0-100 by a deterministic scorecard. Only signals above the **hard floor (default 65)** survive. Survivors are ranked; only the **top 1-3** advance to the LLM pipeline. Everything else is logged to `data/conviction_log/` with its score and the reason it didn't advance, then dropped.

**Stage 2 — Full conviction verdict (Tier 0 + Tier 2, runs only on the 1-3 survivors after Insight + debate).** Combines the deterministic score with debate margin, thesis quality, and source calibration into a final conviction score. The trade proceeds only if the final score clears the **execution floor (default 72)**.

### 6.2 The deterministic scorecard (Stage 1)

Each factor scored 0-100, then weighted. Weights are hot-reloadable in `config.yaml`.

| Factor | Weight | What earns a high score |
|---|---:|---|
| Setup textbook-quality | 20% | Entry conditions met cleanly, not marginally (an ORB break with strong volume, not a 1-tick poke) |
| Regime fit | 15% | Current regime strongly favors this strategy (allocation matrix) |
| Multi-timeframe confluence | 15% | Trend on entry timeframe agrees with higher timeframes; key levels align |
| Volume confirmation | 12% | RVOL elevated; the move has participation, not thin-tape drift |
| Catalyst presence & freshness | 10% | A real catalyst < 15 min old, ≥ 2 sources |
| Liquidity & spread | 8% | Tight spread (<0.3%), high ADV — enter and exit cleanly |
| Risk/reward geometry | 10% | Stop close and logical; target ≥ 1.5R to a real level |
| Strategy recent expectancy | 10% | This strategy's rolling 30-day expectancy is positive |

A signal strong on only one factor scores low and dies. The gate rewards CONFLUENCE — multiple independent reasons to take the trade — the documented antidote to single-indicator bot failure.

### 6.3 The full conviction verdict (Stage 2)

```python
final_conviction = (
    0.45 * deterministic_score +     # Stage 1 scorecard
    0.20 * debate_margin_score +     # (bull_confidence - bear_confidence), scaled
    0.20 * thesis_quality_score +    # Insight Engine falsifiability + driver strength
    0.15 * source_calibration_score  # weighted reliability of contributing agents
)
# Trade only if final_conviction >= execution_floor (default 72)
```

### 6.4 Hard floors that no score can override
A trade is rejected outright if ANY is true: spread > 0.3% of price; stop distance implies 0 whole shares at the risk cap; a catalyst-dependent strategy with no catalyst, or catalyst > 15 min old without confirming volume; a single-source catalyst on a large move; regime = `crisis` and strategy ≠ pairs/cash; within FOMC blackout / first 5 min / last 10 min; the holding window would span an earnings announcement; open positions already at the concurrency cap (3 in Days 1-30, 5 after); daily loss limit, drawdown halt, or budget killswitch active.

### 6.5 The "do nothing" mandate
If no signal clears the floor, the system takes NO trade and reports "no high-conviction setups today" with the highest score it saw and why it fell short. Logged and surfaced on the dashboard. A zero-trade day with a clear log is a SUCCESSFUL day of discipline. Expect zero-trade days regularly, especially in choppy or transitional regimes.

### 6.6 Anti-overtrading guards
- **Daily trade ceiling:** 25 (hard cap), but the TARGET is 1-10. Routinely >10 → Reflector flags it as a symptom to investigate.
- **Cooling-off after a loss:** after any loss the execution floor rises +5 for 30 minutes — the "revenge trade" failure mode is mechanically suppressed.
- **Conviction decay near close:** after 15:00 ET the execution floor rises +3 (less time for a thesis to play out).
- **One-trade-can-be-enough:** the system never feels obligated to "use" its trade budget. A single +3R trade that hits the daily goal means it can stand down.

---

## 7. THE INSIGHT ENGINE — FROM SIGNALS TO FALSIFIABLE THESES

Every trade must be explainable as a thesis with an invalidation condition. This is the "understand the insight that leads to a buy/sell decision" requirement.

### 7.1 The thesis schema
```python
class Thesis(BaseModel):
    ticker: str
    direction: Literal["long", "short"]
    claim: str                  # "AMD breaks above OR high and continues to 145"
    drivers: list[Driver]       # causal-style reasons, each with evidence + weight
    mechanism: str              # WHY this should happen — not just that indicators align
    invalidation: list[str]     # "Loses VWAP", "Breaks back below OR high", "SPY rolls over"
    expected_path: str          # what the next 30-90 min should look like if right
    confidence: float
    base_rate: float | None     # historical hit rate of this setup type in this regime (from memory)
    time_horizon_minutes: int
```

### 7.2 What the Insight Engine does
For each survivor, it (Tier 2, Sonnet) assembles the Tier-0 analyst outputs, the news/sentiment/macro context, and relevant memory into a thesis. Critically: it MUST state a mechanism ("RSI is low" is not a mechanism; "sellers exhausted after a news-driven flush at a weekly support level where buyers have stepped in before" is); it MUST state invalidation conditions (which become the stop logic and management rules); and it MUST anchor to a base rate from memory (if the base rate is 45% and thesis confidence is 80%, that gap is itself a Conviction-Gate warning).

### 7.3 Why this improves decisions
A thesis with a mechanism and an invalidation condition is FALSIFIABLE. The system knows exactly when it's wrong and exits without hesitation. Every trade is auditable: `/why <trade_id>` returns the full thesis, what happened, and whether invalidation fired. Over time the Reflector compares theses to outcomes and the Meta-Learner learns which KINDS of mechanisms actually predict vs which are post-hoc rationalization.

### 7.4 The insight feedback loop
Every closed trade's thesis is scored against reality (did the mechanism drive the move; did invalidation fire correctly; was the base rate accurate). These scores feed memory. Mechanisms that repeatedly predict get promoted to long-term memory; mechanisms repeatedly wrong get demoted. This is how Hood Dabang learns WHY trades work, not just THAT they worked.

---

## 8. STRATEGY LIBRARY — ALL 19 STRATEGIES, FULL SPECS

Each strategy is a class implementing:
```python
class Strategy(ABC):
    name: str
    version: str  # semantic; bumped on any logic change
    activation_status: Literal["development","backtested","paper","live","paused"]
    regime_preferences: dict[str, float]   # {"bull_trend_low_vol": 1.0, "crisis": 0.0, ...}
    requires_llm_gating: bool = True
    def scan(self, universe, market_state) -> list[Setup]: ...
    def manage(self, position, market_state) -> Action: ...
    def stats(self) -> StrategyStats:  # 30-day rolling; drives allocation
```
Activation pipeline: development → backtested → paper → live → (maybe) paused. To go paper→live: all five validation gates (Section 9) + operator approval. To go →paused: 30-day expectancy < -0.1R OR operator manual.

### Intraday strategies (13)

**1. Opening Range Breakout (ORB).** Window 9:35-10:00 ET entries, exits by 15:30. Define opening range = high/low of first 5 min (aggressive) or 15 min (standard). Requires a catalyst (gap >2%, news, earnings) OR top-20 pre-market RVOL. Long: 1-min close above OR-high with volume >1.5x preceding average; short mirrors. Stop: opposite side of OR ± 0.1×ATR(14,1m). Targets: scale 50% at 1.5R, trail rest at 9-EMA. Edge: overnight information expresses early; direction persists 1-2 hours. Failure modes: chop days, FOMC days, half-days — avoid when SPY pre-market within ±0.2% of prior close. Regime: favored in trend regimes, avoided in range.

**2. Initial Balance Breakout (IBB).** First 60-min range. Enter on second test of IB extremes if the first was rejected; on first test if accompanied by news. Stop opposite side of IB. Edge: prop-firm classic; the first hour establishes value, breakouts continue on volume. Regime: trend.

**3. VWAP Mean Reversion.** Window 10:30-15:00. Liquid stock (>5M ADV) trades >2σ from session VWAP; no fresh news in last 30 min; RSI(14,5m) confirms (>75 short, <25 long); wait for first 1-min reversal candle with rising volume. Stop beyond the extreme ± 0.1×ATR. Target VWAP touch. Edge: algorithmic flow creates overextensions that revert. Regime: range only; avoid on trend days.

**4. Gap Fill (mean reversion).** Window 9:30-10:30. Pre-market gap 1-3% on a liquid name, NO confirming news. Wait for a 5-min stall (lower high / higher low against the gap), enter on first 1-min counter-bar. Target prior close (gap level). Stop beyond pre-market extreme. Edge: catalyst-less gaps fill ~70% same day. Regime: any with VIX <20.

**5. Gap and Go (continuation).** Pre-market gap >3% WITH confirmed news. 5-min consolidation after open, enter on break in gap direction. Stop opposite side of consolidation. Target 1.5R + trail. Edge: news-driven gaps with volume continue. Regime: bull trend.

**6. Relative-Volume Momentum.** Window 10:00-14:00. Stock in top-10 intraday RVOL, trending on 5-min (above rising 9-EMA and 20-EMA). Enter on pullback to 9-EMA with volume confirmation. Stop below 20-EMA or recent swing low. Targets 1.5R + trail with 9-EMA. No new entries after 14:00. Edge: unusual volume = unusual interest; pullbacks attract continuation flow. Regime: trend, low-vol.

**7. Earnings Reaction (Day 1).** Stock reported AMC yesterday or BMO today. Wait 15-30 min for price discovery. If up >5% holding above open on strong volume → continuation long on pullback to VWAP. If gap-up reversed below open by 10:00 → short on retest of VWAP from below. Tight stop (ATR-based, max 1.5% from entry). Target 1.5-2R. Edge: post-earnings reaction establishes a clean directional move once initial vol dissipates. Regime: any except crisis.

**8. Catalyst Scalp.** Anytime on hard news (FDA, M&A, guidance, tier-1 desk action, macro print on rate-sensitive names). HALF-size (0.75% risk). Tight stop (0.5% from entry). Quick target (1R). Hit rate likely 45-50% — the edge is asymmetry, not accuracy. `requires_llm_gating` may be relaxed for clean prints.

**9. Range Compression (squeeze → expansion).** 5-min Bollinger Band width < 20th percentile of trailing 100 bars. Enter on first bar breaking the consolidation with volume confirmation. Stop opposite side of consolidation. Target prior swing or 2× consolidation height. Edge: documented ~85% probability of range expansion after extreme contraction. Regime: low-vol.

**10. Hourly Sweep Return-to-Open.** Current hour opens inside the prior hour's range, then sweeps the prior high or low; enter on reclaim of the swept level; target current hour open; stop 0.15×ATR beyond sweep. Best on mechanically-behaved liquid names (SPY, QQQ, AAPL, MSFT, NVDA). Edge: documented return-to-open probability after an hourly sweep.

**11. Multi-Timeframe Engulfing.** A 15-min engulfing candle at a higher-timeframe (1H/daily) support or resistance level, volume >1.5x average. Enter next bar open. Stop beyond the engulfing low (long) / high (short). Target prior swing. Edge: engulfing reversals at HTF levels with volume have documented edge.

**12. Sector Rotation (intraday).** Identify the top-performing sector ETF on the day (XLK, XLE, XLF, XLV, XLY, XLP, XLI, XLU, XLB, XLRE, XLC); within it, find the highest-RVOL liquid name; apply an ORB or Momentum entry. Edge: intraday sector leadership persists for hours. Regime: bull trend.

**13. Short Squeeze.** Short interest >20% of float (refreshed bi-monthly) + RVOL >3x + breaking a key technical level. HALF-size. Wider stop, tight 60-min time stop. High-variance; cap at one trade/day. Regime: bull or any.

### Swing / multi-day strategies (5) — available after Day 30 of live operation

**14. Post-Earnings Drift (PEAD, 2-15 day hold).** Edge: Bernard & Thomas (1989); 30+ year academic anomaly; ~25-30% of the drift happens in the 3-day windows around subsequent earnings. Entry: Day 2 after earnings (skip Day-1 noise) on stocks with Standardized Unexpected Earnings (SUE) > 1.0 (top-quintile beat) AND relative-strength rank top 30% in sector over prior 5 sessions. Hold 5-15 days, trailing stop or 10-day time stop. Size 0.75% risk. Exit: 1.5R on half, trail rest with daily 9-EMA, force exit Day 15.

**15. Momentum Swing (3-10 day hold).** Edge: Jegadeesh & Titman momentum factor. Entry: top-decile 20-day price momentum AND breaking a 20-day high on volume >1.5x 20-day average AND above a rising 50-day SMA. Hold 3-10 days. Size 1% risk. Exit: 2R on half, trail rest with 20-day SMA; force exit on a close below the 20-day SMA.

**16. Earnings Beat Follow-Through (5-day hold).** Edge: magnitude of beat correlates with sustained drift. Entry: Day-1 close above the day's open after a top-decile beat AND a guidance raise (parsed from the press release); buy at next day's open. Hold 5 days. Size 0.75% risk. Exit: 1.5R, 5-day time stop, or trailing 2-ATR stop.

**17. Quality Mean Reversion Swing (3-5 day hold).** Edge: high-quality large-caps that drop on indiscriminate selling recover within a week. Entry: S&P 100 constituent AND RSI(2) < 5 (extreme oversold) AND price within 5% of the 200-day SMA AND no fresh negative catalyst. Hold 3-5 days. Size 0.75% risk. Exit: reversion to 5-day SMA, 3-day time stop, or -1.5R stop.

**18. Sector Momentum Rotation (1-2 week hold).** Edge: sector leadership persists over multi-week horizons. Entry: top-performing sector ETF over trailing 4 weeks AND broadening breadth (>60% of sector members above their 20-day SMA); take the highest relative-strength liquid name in that sector. Hold 1-2 weeks. Size 0.75% risk. Exit: sector ETF closes below its 20-day SMA, 3R target, or 14-day time stop.

### Statistical arbitrage (1)

**19. Pairs Statistical Arbitrage.** Two correlated names (e.g., MSFT/GOOGL, MA/V, XOM/CVX). Compute the spread's rolling z-score; enter when |z| > 2σ (long the underperformer, short the outperformer); exit on revert to 0 or stop at 3σ. Market-neutral. Edge: spread mean-reversion. Regime: the only strategy that runs meaningfully in CRISIS (60% allocation) because it doesn't depend on market direction.

### Regime-conditioned allocation matrix (abbreviated; full 20-row × 8-column matrix in config.yaml)
Daily risk budget = 5 × Kelly-derived per-trade max. Crisis → mostly cash + pairs. Allocations re-weighted weekly by rolling 30-day per-strategy-per-regime expectancy. Even a favored strategy in a favored regime only gets capital when a specific setup clears the Conviction Gate.

| Strategy | Bull/LowVol | Range/LowVol | Bear/HighVol | Crisis | Transitional |
|---|---:|---:|---:|---:|---:|
| ORB | 15% | 5% | 10% | 0% | 5% |
| VWAP Reversion | 5% | 20% | 5% | 0% | 10% |
| Gap Fill | 10% | 15% | 5% | 0% | 10% |
| Momentum (intraday) | 12% | 5% | 5% | 0% | 5% |
| Momentum Swing | 10% | 0% | 0% | 0% | 5% |
| PEAD | 5% | 5% | 5% | 0% | 0% |
| Earnings Beat F/T | 5% | 5% | 5% | 0% | 0% |
| Quality Mean Rev Swing | 0% | 5% | 5% | 0% | 5% |
| Range Compression | 5% | 15% | 5% | 0% | 10% |
| Catalyst Scalp | 5% | 5% | 10% | 0% | 5% |
| Pairs Stat-Arb | 0% | 0% | 5% | 60% | 20% |
| Cash | balance | balance | balance | 40% | balance |

---

## 9. STRATEGY VALIDATION — THE FIVE GATES

Because backtest Sharpe predicts live performance at R² < 0.025, a single backtest is meaningless. Every strategy must pass, in order, before it trades real money. Enforced in code: the registry refuses to mark a strategy `live` unless all five flags are set in `data/trader.db`.

1. **Walk-forward validation.** Train on 6 months, validate on the next 1 month, roll monthly. Positive expectancy in ≥70% of validation windows.
2. **Bootstrap overfit test** (Bailey et al., 2016). 5,000-trial bootstrap on the trade sequence. Probability of Backtest Overfitting (PBO) ≤ 0.05.
3. **Deflated Sharpe Ratio (DSR).** Sharpe deflated for the number of strategy variants tried and the non-normality of returns must be statistically > 0 at 95% confidence. Direct antidote to "we tried 50 variants and one looked great by chance."
4. **Out-of-sample within 50% of in-sample.** Out-of-sample expectancy ≥ 50% of in-sample expectancy. A larger gap means overfitting.
5. **Forward paper period.** ≥30 paper trades on LIVE (not historical) data with positive expectancy and 100% rule adherence.

Anti-overfitting discipline: never optimize a parameter on the same data that proved the edge; change one parameter at a time; require ≥10 trades of new evidence before declaring a change successful; a monotonic, low-drawdown backtest is a WARNING (add simulated slippage, missed fills, and news delays and verify the edge survives); always report max drawdown, longest losing streak, Sharpe, Sortino, Calmar, hit rate, average R, and expectancy — never just cumulative returns.

---

## 10. POSITION SIZING — KELLY, VOL-TARGETED, CORRELATION-CAPPED, CONVICTION-SCALED

### 10.1 Kelly fraction from the journal
For each strategy the journal yields p (empirical win rate, recency-weighted), b (avg_win / avg_loss), and f* = (bp − q)/b where q = 1−p. Use HALF-KELLY (quarter-Kelly for strategies with <30 trades). Full Kelly is mathematically optimal but practically too aggressive — small errors in p or b flip optimal growth to ruin. Half-Kelly cuts variance ~half while preserving ~75% of geometric growth.
```python
def kelly_size(strategy, equity):
    s = strategy.stats()
    if s.n_trades < 30:
        return min(0.005, default_risk_pct) * equity   # 0.5% until proven
    p = s.win_rate
    b = s.avg_win_dollars / s.avg_loss_dollars
    f_star = (b*p - (1-p)) / b
    half_kelly = max(0, f_star) * 0.5
    return min(half_kelly, 0.015) * equity              # hard cap at 1.5%
```

### 10.2 Volatility targeting
Target 10-15% annualized portfolio vol from the trailing 20-session equity curve. High realized vol → scale down; low → scale up (within Kelly cap).
```python
def vol_adjusted(base, realized_vol_20d, target=0.12):
    if realized_vol_20d <= 0: return base
    return base * min(1.5, target / realized_vol_20d)
```

### 10.3 Correlation cap
Two positions correlated >0.7 (rolling 60-day) count as ONE position for exposure. Prevents the LTCM failure where "diversification" wasn't real because everything moved together under stress.

### 10.4 Conviction scaling (the v5 addition)
Within the Kelly cap, size scales with the final conviction score: ~60% of Kelly at the execution floor (72), 100% at conviction 90+. Capital concentrates in the best ideas — which is how one good trade meaningfully moves the needle.
```python
def conviction_scaled(kelly_allowed, conviction, floor=72):
    ratio = 0.6 + 0.4 * min(1.0, (conviction - floor) / (90 - floor))
    return kelly_allowed * max(0.6, ratio)
```

### 10.5 Final size = minimum of all constraints
```
final = min(kelly_size, vol_adjusted, conviction_scaled,
            0.30*equity,                 # max single position
            available_risk_budget(),     # daily budget remaining
            correlation_adjusted_room())  # correlation cap
```
The minimum always wins. Whole shares only. Swing strategies use a smaller base (0.75% risk) due to longer holds.

---

## 11. LAYERED MEMORY ARCHITECTURE (FinMem design)

- **Working memory (per session):** today's brief; open positions and their theses; today's fills and reasoning; active hypotheses.
- **Short-term (last 5 sessions):** recent outcomes by strategy; recent regime calls and their accuracy; recent agent outputs and their correlation with realized returns; operator interventions.
- **Medium-term (last quarter, ~60 sessions):** strategy performance per regime; recurring catalysts and how affected names behaved; sector behavior; calendar effects (Fed, OPEX, earnings seasons).
- **Long-term (persistent):** validated patterns ("RVOL>3 + news + above VWAP → ORB long expectancy 0.42R"); validated failure modes ("FOMC days, entries before 14:30 underperform"); operator preferences.

**Retrieval:** `score = 0.3·decay(timestamp) + 0.5·cosine(query, memory) + 0.2·importance` (importance tagged at write: routine=1, surprising=3, lesson=5). Embeddings local (sentence-transformers), free.

**Consolidation (weekly):** patterns observed ≥3 times with consistent outcome graduate to long-term; long-term patterns contradicted ≥2 times demote to medium-term for re-validation; patterns surviving 90 days of confirmation are marked "stable" (immutable until 5+ contradictions).

**Never store:** account credentials; anything that could be material non-public information; personal data beyond trading-relevant preferences.

---

## 12. SELF-IMPROVEMENT ARCHITECTURE

- **Golden samples:** held-out historical scenarios with known good answers — 200 "perfect ORB," 150 "obvious skip," 100 "watch don't trade," 50 "news catalyst response," 30 regime-transition, 20 "agent should refuse" (prompt injection / malformed input). The Reflector adds new scenarios from real trades that were especially instructive.
- **LLM-as-judge:** nightly, each agent scored on its golden samples (mean, stddev, Brier calibration, clustered failure modes). Stable judge prompt; two judges disagreeing → human review.
- **Meta-prompting:** when an agent regresses, the Meta-Learner proposes ≤5 revised prompts, tests them on the golden set, and promotes one to `staging` only if it beats current by a significant margin (p<0.05, n≥30). A revised prompt 50% longer must show >50% improvement (cost is part of the criterion).
- **Shadow mode (canary):** a new prompt/strategy version runs IN PARALLEL with live for one trading week, consuming the same inputs but emitting no orders. Shadow ≥ live + threshold → promote; shadow < live → discard and investigate; tie → extend a week. A new code path is NEVER live without first proving itself in parallel (the Knight Capital defense).
- **A/B testing on the live tape:** for strategy logic changes, the shadow runs on real-time data emitting no orders; after ≥30 "would-have-fired" instances, statistical comparison decides promotion.
- **Adversarial self-testing (monthly):** the Meta-Learner generates scenarios designed to trip the system (data quality issues, prompt injection, missing fields, broker edge cases); failures become permanent tests in `tests/`.
- **The recursive constraint:** the Meta-Learner CANNOT modify `src/risk.py`, `src/killswitch.py`, `src/reconciliation.py`, strategy version locking, `tests/test_*.py`, or the Conviction-Gate floors. A system that can improve its own kill switch will eventually disable it. Self-improvement happens around the bedrock, never through it.
- **Conviction-floor tuning:** the weekly review tunes the gate's weights and floors — if trades that just cleared the floor underperform while higher-conviction trades win, the floor rises; if the system is rejecting setups that would have won, it lowers. Bounded to 65-80, logged, and run in shadow before going live.

---

## 13. RISK MANAGEMENT — THE NON-NEGOTIABLE LAYER

Every order passes through `src/risk.py` before execution. The risk gate cannot be overridden by any agent — only by the operator via `MANUAL_OVERRIDE.flag` with a 24-hour cooldown. Certain rules (loss limit, max position) are flagged IMMUTABLE in code.

**Per-trade:** max risk = half-Kelly, ≤1.5% of equity; position size = floor(max_risk_dollars / |entry − stop|), whole shares; max position notional 30% of equity; mandatory stop loss placed as a separate broker order immediately after fill (if rejected, immediately flatten); mandatory target or trail rule; reject if spread > 0.3% of price; strategy expectancy must survive a 0.05% slippage assumption.

**Daily:** loss limit -5% of session-start equity (hit → cancel orders, flatten, halt session, loud notification, journal entry); soft profit cap +20% (hit → "tighten and trim": stops to break-even, no new entries except A+); trade frequency cap 25/session (target 1-10); concurrent positions ≤3 in Days 1-30, ≤5 after; total exposure ≤80% of equity (intraday-only Days 1-30).

**Account-level:** drawdown halt at equity ≤80% of all-time high (operator resume required); catastrophic halt at equity ≤70% of starting capital ($1,050) (indefinite, full review); connection halt (MCP heartbeat fails >60s → 3 retries → flatten on reconnect → halt session); reconciliation halt (broker ≠ internal >1 cycle → halt); cooldown halt (5 consecutive losses → 30 min, 8 → day).

**P&L velocity (Knight Capital defense):** internal P&L monitored every second — if unrealized P&L moves >3σ vs its trailing 60-second baseline → pause new orders, verify state, alert; order rate exceeding the 95th percentile of history → freeze; any activity on a ticker not on today's watchlist → freeze and reconcile.

**Condition-specific:** FOMC blackout (14:00-14:30 ET on FOMC days) → no entries, tighten stops to break-even; CPI/NFP/PPI morning (8:30 ET print) → no entries until 9:45; never hold through an earnings announcement; half-days / day-before-holidays → 50% size reduction; OPEX (third Friday) → tighter stops on index-related names.

**Order hygiene:** preview before placing when the MCP supports it (log preview, verify intent match, then submit); marketable limit orders only, never market; cancel-replace stale limits (>30s unfilled); idempotent order IDs so retries don't double-fire; verify fills by querying account post-submit — any mismatch → halt and reconcile.

---

## 14. KILLSWITCHES — ALL 26

`src/killswitch.py` evaluates these every tick. All halts are loud, all write a journal entry, most require operator action to resume. KillEvent jumps the bus.

| # | Condition | Action |
|---|---|---|
| 1 | Daily loss ≤ -5% of session-start | Flatten, halt session |
| 2 | Drawdown ≤ -20% from ATH | Flatten, halt until operator resume |
| 3 | Catastrophic ≤ $1,050 | Flatten, halt indefinitely, require review |
| 4 | MCP failure > 60s | 3 retries; flatten on reconnect; halt session |
| 5 | Reconciliation desync > 60s | Halt, manual reconcile |
| 6 | Data feed stale > 30s on open position | Tighten stop to current; no new positions |
| 7 | Database integrity check fail | Halt, notify |
| 8 | HALT.flag exists | Halt immediately |
| 9 | 5 consecutive losses | 30-min cooldown |
| 10 | 8 consecutive losses | Halt for the day |
| 11 | Quote moves >10% in 5s without volume + news | Pause ticker, verify |
| 12 | 3 consecutive order rejections | Halt, investigate |
| 13 | P&L velocity anomaly | Pause new orders, reconcile |
| 14 | Order to ticker not on watchlist | Block, freeze, reconcile |
| 15 | Self-test failure | Halt, notify |
| 16 | Feature flag past expiration | Block startup |
| 17 | Time-based (market closed, FOMC blackout, holiday) | Halt |
| 18 | Backtest-live parity violation | Halt, notify |
| 19 | Memory corruption / retrieval failure | Halt, notify |
| 20 | Calibration drift (confidences uncorrelated with outcomes) | Reduce that agent's weight; notify |
| 21 | Daily LLM budget exceeded ($5) | BUDGET_PAUSE.flag; pause LLM agents; Tier 0 continues |
| 22 | Monthly LLM budget exceeded ($60) | Pause LLM agents; require operator review |
| 23 | LLM provider outage (3 timeouts/60s) | Graceful degradation; no execution halt |
| 24 | Cache poisoning (same hash → different behavior) | Invalidate entry; repeated → halt |
| 25 | Conviction bypass (trade reached Execution without a ConvictionEvent above floor) | Halt immediately |
| 26 | Thesis-less trade (OrderEvent with no stored thesis) | Halt immediately |

Operator removes HALT.flag and runs `python -m src.controller --resume`.

---

## 15. SELF-TESTS — ALL 26 (MUST PASS BEFORE LIVE; NIGHTLY THEREAFTER)

1. No-look-ahead (synthetic future-data trap; strategy must produce the same output as if blind to the future). 2. Backtest-live parity (same code, same inputs, identical orders in both modes). 3. MCP schema (every call validated against the actual MCP schema; hallucinated params fail). 4. Reconciliation (simulated desync fires the killswitch). 5. Risk caps (orders exceeding each cap rejected; verify every cap). 6. Killswitch (each condition tested with synthetic inputs). 7. Dead-code detection (paths not exercised in 30 days flagged — Knight Capital). 8. Feature-flag expiration (expired flag fails build). 9. Survivorship (today's universe fed to a 1-year backtest must fail). 10. Slippage (simulated fills include modeled slippage; model matches realized within 50%). 11. Memory retention (seeded facts retrieved with expected scores). 12. Agent calibration (an agent's "0.7 confidence" correct ~70% on held-out; Brier below threshold). 13. Golden-sample regression (all agents above 90% of their 7-day baseline). 14. Order idempotency (same OrderEvent twice → one order). 15. LLM cost accounting (ledger sum matches billed within 1%). 16. Cache hit rate (>70% over a session). 17. Tier compliance (every call's model matches the agent's declared tier). 18. Local latency (each Tier-0 analyst < 500ms). 19. Graceful degradation (simulated LLM outage; Tier 0 continues, open positions managed). 20. Conviction floor (signals below floor never reach the LLM pipeline; hard-floor violators rejected regardless of score). 21. Conviction ranking (given 10 signals, exactly the top 1-3 advance). 22. Thesis falsifiability (every thesis has a non-empty mechanism + ≥1 invalidation; else rejected). 23. Validation-gate enforcement (registry refuses `live` without all five gate flags). 24. Deflated Sharpe (DSR matches a reference value on fixed input). 25. Conviction-scaled sizing (size scales 60%→100% of Kelly between floor and conviction 90). 26. Revenge-trade suppression (after a simulated loss, a marginal signal that would have passed is rejected during the 30-min cooling window).

Nightly: all. Pre-market: 1-6, 20-23. Pre-trade (per order): risk caps, idempotency, conviction hard floors. Any failure → halt + notify.

---

## 16. THE DAILY RHYTHM

**7:30 ET — Wake.** Health checks (MCP, feeds, disk, DB, network); LLM ledger reconciled; self-test suite (all 26); pull overnight data (Tier 0).
**8:00-8:30 ET — Research pipeline.** Tier 0 first (insider Form 4, macro data, earnings calendar, regime model). Then Tier 1 (news + sentiment batched, cached). Then Tier 2 (macro synthesis; fundamentals on-demand).
**8:30 ET — High-impact macro releases.** Notification only. No trades off the release. Wait until 9:45.
**9:00 ET — Watchlist + deterministic scoring.** Screener builds 20-50 names; Tier-0 analysts score all. No LLM yet.
**9:25 ET — Morning brief published, cache primed.** Regime, allocations, the names most likely to produce high-conviction setups, the day's macro risks, things that would invalidate the plan. Saved to data/briefs/. Notification: "Brief ready, N watch names, 0 trades so far — waiting for conviction." Prompt cache populated.
**9:30-9:35 ET — Open, no trading.** OR tracking begins.
**9:35-15:50 ET — Active session (conviction-gated).** Every 1-2s (Tier 0): killswitches; manage open positions; strategies scan; every signal hits the deterministic Conviction Gate; only top 1-3 advance. On a survivor (Tier 2-3): Insight thesis → Bull/Bear debate → Trader synthesis → full Conviction verdict → Risk debate → PM decision → Execution. Every 5 min: rescan (Tier 0), refresh news (Tier 1 if new). Every 60s: reconciliation. Every second: P&L velocity, budget check.
**15:50 ET — Close.** Flatten intraday positions; cancel orders; compute session P&L; notify.
**16:30 ET — Post-market (Tier 2).** Reflector: per-trade reflections + thesis-vs-reality scoring + session reflection. Strategy stats updated. DB backed up.
**21:00 ET — Nightly self-improvement (Tier 3, amortized).** Golden-sample eval (rotated agents); Meta-Learner proposals queued; adversarial sweep; tomorrow's cache pre-warmed.
**Sunday 18:00 ET — Weekly review.** Reflector meta-review; strategy reallocation by per-regime expectancy; conviction-floor tuning; memory consolidation; universe refresh; shadow→live promotions; LLM cost report; operator report sent.

---

## 17. DATA SOURCES — ALL FREE, WITH GRACEFUL DEGRADATION

**Price/volume:** Robinhood MCP (account state + execution); yfinance (free OHLCV 1m-daily, cached); Alpaca free tier and Polygon.io free tier (operator opt-in).
**News (RSS, no paywalled scraping):** Yahoo Finance per-ticker (`https://feeds.finance.yahoo.com/rss/2.0/headline?s={TICKER}&region=US&lang=en-US`), MarketWatch, Reuters Business, SEC EDGAR 8-K full-text search, PR Newswire, Business Wire, Federal Reserve press releases.
**Insider/institutional:** SEC EDGAR Form 4 JSON (`https://data.sec.gov/submissions/CIK{cik}.json`, proper User-Agent, respect fair-use), Form 13F (lagged 45 days), FINRA daily short-volume CSVs (`https://cdn.finra.org/equity/regsho/daily/`).
**Macro:** FRED API (rates, yields, credit spreads, USD index), Treasury.gov yield curve, BLS/Census release calendars, Federal Reserve speakers schedule.
**Earnings:** Nasdaq earnings calendar JSON (free, public), Yahoo Finance fallback.
**Options flow (signal only — no options trades):** yfinance chains (IV, P/C, OI), free UOA snapshots (UnusualWhales/OptionStrat free tiers). Treat as supplementary confirmation; free flow is often delayed.
**Sentiment:** in-house Haiku on aggregated headlines; Reddit official API (rate-limited) r/wallstreetbets mentions + comment sentiment with regime-aware skepticism; StockTwits public API.
**Will NOT use:** paid "AI prediction" services (overfit/fraud); anything requiring Robinhood credentials shared with third parties; scraped paywalled content; Discord/Telegram pump groups; anything promising specific returns.

| Feed | Critical? | If unavailable |
|---|---|---|
| Robinhood MCP | YES | Halt execution. Open positions stay (no way to manage). Notify. |
| yfinance | High | Fall back to MCP quotes; reduce to MCP-data-only strategies. |
| News RSS | Mid | Continue with cached news; reduce catalyst-driven strategies. |
| SEC EDGAR | Low | Pause insider analyst; others continue. |
| FRED | Low | Use cached macro; macro analyst lowers confidence. |
| LLM API | Mid | Graceful degradation; Tier 0 continues; open positions managed. |

---

## 18. THE 28 AI FAILURE MODES + DEFENSES

1. **Look-ahead bias** (most expensive) → event-driven backtester with strict timestamp guards; explicit future-data-trap test; fresh-subagent audit of every strategy. 2. **Survivorship bias** → point-in-time universe. 3. **Overfitting** → walk-forward + bootstrap PBO + DSR. 4. **Data handling** (splits, dividends, timezones) → normalization layer with assertions; ET default. 5. **Transaction-cost neglect** → realistic slippage model; realized vs modeled tracked quarterly. 6. **Hallucinated MCP calls** → schema validation on every call; fabricated-looking responses halt. 7. **State desync** → reconciliation every 60s. 8. **Prompt injection via news** → news is data, never instructions; articles delimited; instruction-like content classified, not executed. 9. **Sycophancy toward operator** → risk caps require MANUAL_OVERRIDE.flag + 24h cooldown. 10. **Black-box opacity** → full reasoning trail per trade; `/why <id>`. 11. **Concept drift** → weekly expectancy review; regime residual monitor; auto-pause negative-expectancy strategies. 12. **Forced trades to hit a number** → PM mandate prohibits it; Reflector flags "make up earlier loss" reasoning. 13. **News latency** → news >15 min downweighted; no catalyst trades on stale news without confirming volume. 14. **Spoofed news** → ≥2 independent sources for any catalyst trade. 15. **Dormant code** (Knight Capital) → paths unexercised 30 days flagged; feature flags require expires_at; expired flags fail build. 16. **Deployment errors** (Knight Capital) → deployment checksum; code-on-disk must match expected hash or refuse to start. 17. **Order amplification** (Knight Capital) → P&L velocity monitor; order-rate freeze. 18. **Correlated tail risk** (LTCM) → correlation cap at 0.7; stress test before sizing up. 19. **Calibration drift** → Brier tracked per agent; drifted agents downweighted in the gate. 20. **Backtest-live divergence** (NautilusTrader) → identical code paths; parity test. 21. **Reward hacking by Meta-Learner** → cannot modify risk/killswitch/reconciliation/tests/gate floors; promotion needs golden improvement + a shadow week. 22. **Memory poisoning** → writes only by Reflector + system; long-term items need ≥3 consistent observations; demoted on contradiction. 23. **Token budget runaway** → per-call cost logged; cumulative tracked every second; hard halt at budget cap. 24. **Tier escalation by accident** → every call's model validated against declared tier; mismatch halts. 25. **Cache stale drift** → cache TTLs; classifications >1 trading day re-checked; conflicting classifications investigated. 26. **Local model staleness** → regime residuals tracked; HMM/RF retrained from last 60 sessions overnight if residual exceeds threshold. 27. **Tier-0 latency creep** → every Tier-0 call timed; alert if >500ms. 28. **Post-hoc rationalization** → the thesis must state mechanism + base rate BEFORE the Trader's final synthesis; the Reflector later scores whether the mechanism actually drove the move; the gap between thesis confidence and historical base rate is itself a gate input.

**Two elevated to first-class:** Overtrading (the entire Conviction Gate + anti-overtrading guards — the most-cited 2026 failure mode) and Backtest over-trust (the five validation gates + DSR — the 888-strategy R²<0.025 finding).

---

## 19. HONEST BENCHMARKS

| Phase | Duration | Target | "Good" means |
|---|---|---|---|
| Ramp | Wk 1-2 | Rule adherence + conviction discipline | 100% rule adherence; comfortable zero-trade days; every trade has a thesis |
| Calibration | Wk 3-4 | $10-30/day avg | Positive expectancy; high variance; 1-5 trades/day |
| Stabilization | Mo 2 | $30-60/day avg | Reallocation working; swing strategies unlock Day 30 |
| Multi-mode | Mo 2-3 | $50-100/day OR larger swing wins | Some weeks' gains come from 1-2 swing trades |
| Performance | Mo 3+ | $50-100/day avg, ≤15% max-month DD | On par with best documented agentic results |
| Stretch | Mo 4-6 | $100+/day avg | Above documented systems |
| Failure | Any | 3 consecutive negative months | Halt; full review |

Net accounting: $100/day gross − ~$1.80 LLM − ~$0.80 slippage − $0 fees ≈ **$97/day net**.
Reference points: Renaissance Medallion ~4.2%/month (with leverage + infrastructure we lack); best 2026 agentic live ~10%/month over 90 days; TradingAgents ~7%/30d with 22% DD. $100/day on $1,500 = 6.67%/day exceeds every sustained documented system — treat it as aspiration with the phase targets as the real KPIs. Hitting Month-2 ($30-60/day avg) already beats the published agentic literature.

---

## 20. MONITORING — THE TERMINAL DASHBOARD

Built with `rich` (works on any Mac terminal, no GUI deps). Refresh 1s. Color-coded (green profit, red loss, yellow warning). `--quiet` for headless; `--verbose` adds the event-bus stream and per-agent token usage.

```
┌─ HOOD DABANG ──────────────────── 14:32:07 ET ──── REGIME: BULL/LOW-VOL ──┐
│ Equity: $1,567.20  Day P&L: +$67.20 (+4.48%)  ATH: $1,672.40              │
│ Trades today: 2 (target 1-10)  Win: 2/2   Conviction floor: 72 (+0 adj)    │
│ DD from peak: -2.1%  Loss remaining: $7.80  Cooldown: NO                    │
├─ CONVICTION GATE (today) ───────────────────────────────────────────────────┤
│ Signals seen: 41  Cleared Stage-1 floor: 6  Reached LLM: 3  Traded: 2      │
│ Highest score not taken: AMD ORB 69 (below execution floor 72)             │
│ Current candidate: NVDA VWAP-reversion det-score 74 → in debate            │
├─ ACTIVE THESES ─────────────────────────────────────────────────────────────┤
│ AAPL long: "OR break + AI-news momentum to 191" inval: loses VWAP          │
│   base rate 58% · confidence 71% · status: T1 hit, trailing                │
│ NVDA short: "2σ VWAP overextension, seller exhaustion" inval: reclaims VWAP │
│   base rate 61% · confidence 66% · status: working                         │
├─ COSTS (today / month) ─────────────────────────────────────────────────────┤
│ LLM today: $1.12 of $5.00  ▓▓░░░░░░░░ 22%   Cache hit: 83%                  │
│ Month-to-date: $34.10 of $60   Net P&L after costs: +$291                   │
├─ AGENTS (last invocation · calibration) ────────────────────────────────────┤
│ Regime 14:30 0.84 · Macro 09:15 0.71 · News 14:29 0.82 · Insider 08:45 0.68 │
│ Microstructure 14:30 0.74 · Technical 14:31 0.86 · Sentiment 14:30 0.65     │
│ Bull 14:25 0.79 · Bear 14:26 0.77 · Trader 14:27 0.80 · PM 14:28 0.83       │
│ Meta-Learner staging: news_v2.3 (shadow day 3/5, +0.04 vs live)            │
├─ POSITIONS (2 open) ────────────────────────────────────────────────────────┤
│ AAPL +50 @189.43 →191.10 (+0.88%) Stop:188.90 T1:190.85 ORB v2.1           │
│ NVDA -20 @921.05 →919.10 (+0.21%) Stop:924.50 T1:917.00 VWAP v1.4          │
├─ WATCHLIST (top 5) · TODAY'S TRADES · MORNING BRIEF ────────────────────────┤
│ (RVOL, news flags, setup status per name; fills with R-multiples; regime)  │
├─ SYSTEM HEALTH ─────────────────────────────────────────────────────────────┤
│ MCP ✓12ms  Data ✓1.2s lag  News ✓  DB ✓  Memory ✓12 long-term             │
│ Killswitch: ARMED  Override: OFF  Self-tests: ✓26 green  Backups ✓16:30    │
└──────────────────────────────────────────────────────────────────────────────┘
```
The conviction panel makes "quality over quantity" visible: how many signals were rejected, why, and the highest score that didn't clear the bar.

---

## 21. NOTIFICATIONS

macOS native via `osascript -e 'display notification "..." with title "..." sound name "Glass"'`. No extra deps.
**Notify on:** pre-market brief ready (08:55, quiet); each trade entry/exit (quiet, details); stop hit (louder); daily target reached (celebratory, once); daily loss approaching $60-of-$75-equivalent (warning); daily loss hit (loud + halt); drawdown halt (loud); catastrophic halt (loudest); MCP disconnect (loud); self-test failure (loud); P&L velocity anomaly (loud); LLM budget 75% today/month (quiet); LLM budget hit (loud); LLM provider outage (quiet, degradation active); "No high-conviction setups today" (EOD, quiet — a normal, healthy outcome); Meta-Learner promoted a version (quiet digest); EOD summary (16:30, quiet); weekly report (Sunday 18:00, quiet).
**Optional channels** (config.yaml): email (SMTP), Telegram (bot token), SMS (Twilio), Slack (webhook).
**Anti-fatigue:** suppress routine scanner/agent ticks and watchlist refreshes. Two phone glances/day = full awareness.

---

## 22. OPERATOR INTERFACE — SLASH COMMANDS

```
/status        current state in one screen
/halt          stop trading immediately
/resume        resume from halt
/flatten       close all positions now
/why <id>      full reasoning trail + thesis for a trade
/review <date> a session's journal and stats
/strategy <name> on|off
/explain       current regime + watchlist + active setups
/journal       today's journal
/risk          current risk usage (per-trade, daily, drawdown)
/calibration   agent calibration scores
/shadow        what's in shadow mode and its performance vs live
/promote <component> <version>
/rollback <component>
/golden add    add a recent scenario to golden samples
/budget        LLM cost ledger today + month, by agent
/budget set <amount>   change daily LLM budget (logged)
/tier <agent> show     which model an agent uses
/degrade <feed>        manually mark a feed degraded (testing)
/restore <feed>
/conviction            today's gate stats: seen, cleared, traded, highest-not-taken
/conviction floor <n>  adjust execution floor (logged; within 65-80)
/thesis <id>           the full falsifiable thesis for a trade
/rejected              today's rejected signals with scores and reasons
/why-no-trade          explain why the system hasn't traded (if it hasn't)
```
`config.yaml` hot-reloads every 60s. Sensitive params (loss caps, position max, killswitch thresholds, budget caps, conviction hard floor) require `MANUAL_OVERRIDE.flag` + 24h cooldown.

---

## 23. OPERATIONAL LIFECYCLE — START, STOP, RECOVER, SCHEDULE

### 23.1 First-time setup (one-time)
```bash
brew install python@3.11 sqlite
npm install -g @anthropic-ai/claude-code

mkdir -p ~/hood-dabang && cd ~/hood-dabang
# Save BRIEF.md (this file) here

python3.11 -m venv .venv
source .venv/bin/activate
pip install -U rich pydantic httpx loguru pandas numpy yfinance feedparser \
    python-dotenv anthropic scipy scikit-learn hmmlearn sentence-transformers \
    aiohttp aiosqlite pytz pyyaml ta-lib-binary

claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading

cp config.yaml.template config.yaml      # operator edits parameters
cp .env.template .env                    # add ANTHROPIC_API_KEY

claude --model opus
# Inside Claude Code: "You are building Hood Dabang. Read BRIEF.md. Execute Section 27 (Bootstrap)."
```

### 23.2 Daily startup (manual)
```bash
cd ~/hood-dabang
source .venv/bin/activate
python -m src.controller
```
The controller checks for HALT.flag (refuses to start if present), runs the 26 self-tests, starts the event loop if all pass, opens the dashboard, and begins the daily rhythm.

### 23.3 Daily startup (automated via launchd on macOS)
Create `~/Library/LaunchAgents/com.hooddabang.controller.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.hooddabang.controller</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/hood-dabang/.venv/bin/python</string>
        <string>-m</string><string>src.controller</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/YOUR_USER/hood-dabang</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>15</integer></dict>
    <key>RunAtLoad</key><false/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/><key>Crashed</key><true/></dict>
    <key>StandardOutPath</key><string>/Users/YOUR_USER/hood-dabang/logs/launchd.out.log</string>
    <key>StandardErrorPath</key><string>/Users/YOUR_USER/hood-dabang/logs/launchd.err.log</string>
</dict>
</plist>
```
Activate: `launchctl load ~/Library/LaunchAgents/com.hooddabang.controller.plist`
Now the controller starts at 7:15 ET every weekday and auto-restarts if it crashes. (StartCalendarInterval without a Weekday key runs daily; the controller's own time-based killswitch #17 keeps it idle on weekends/holidays. To restrict to weekdays at the OS level, add five StartCalendarInterval entries with Weekday 1-5.)

### 23.4 Stopping
```bash
touch ~/hood-dabang/HALT.flag        # graceful — wait for "halt confirmed" notification
pkill -f "src.controller"            # hard stop if graceful doesn't respond within 60s
launchctl unload ~/Library/LaunchAgents/com.hooddabang.controller.plist   # disable auto-start
```
After HALT.flag, open positions remain. To close them too: `python -m src.ops.shutdown --flatten` before stopping.

### 23.5 Resuming after halt
```bash
rm ~/hood-dabang/HALT.flag
python -m src.controller --resume
```
`--resume` forces reconciliation: broker state is fetched, internal state is rebuilt from data/trader.db, any divergence requires operator confirmation before trading resumes.

### 23.6 Recovery from crash / power loss
On every startup the controller: (1) checks HALT.flag (refuse if present); (2) loads last state from data/trader.db; (3) connects to MCP, fetches broker state; (4) reconciles — any divergence halts and asks the operator; (5) runs the 26 self-tests; (6) halts and asks on any failure; (7) if all green, resumes per the daily rhythm (in-session vs out-of-session). SQLite is in WAL mode, so state is consistent across power loss.

### 23.7 Network outage
MCP heartbeat fails >60s → killswitch #4 (3 retries; flatten on reconnect; halt session). LLM API fails → graceful degradation (Tier 0 continues, open positions managed, no new LLM-gated entries, operator notified). yfinance/news fail → Section 17 degradation table (reduced strategy set, continue).

### 23.8 Config hot-reload
config.yaml reloads every 60s. Sensitive params require MANUAL_OVERRIDE.flag + 24h cooldown.

---

## 24. WHAT TO READ — CURRICULUM

The Meta-Learner schedules one item per week and asks the Reflector to summarize how it applies to Hood Dabang.
**Multi-agent & self-improvement:** TradingAgents (arxiv 2412.20138); TradingGPT (2309.03736); FinMem (2311.13743); FinAgent (2402.18485); QuantAgents (aclanthology 2025.findings-emnlp.945); "Toward Expert Investment Teams" (2602.23330); "Reliable Evaluation of LLM-Based Financial Multi-Agent Systems" (2603.27539); Voyager (2305.16291); DreamerV3 / continual RL (2603.04029); "A Survey of Self-Evolving Agents" (2507.21046); OpenAI Self-Evolving Agents cookbook.
**Anomalies & edges:** Bernard & Thomas (1989, 1990) PEAD; "PEAD with genetic-algorithm-optimized supervised learning" (2009.03094); Jegadeesh & Titman (momentum); Lo "Adaptive Markets"; Aronson "Evidence-Based Technical Analysis"; Zuckerman "The Man Who Solved the Market."
**Backtesting & overfitting:** De Prado "Advances in Financial Machine Learning"; Bailey et al. (2016) "The Probability of Backtest Overfitting"; Bailey & López de Prado (2014) "The Deflated Sharpe Ratio"; "Deep RL for Crypto Trading: Practical Approach to Backtest Overfitting" (2209.05559); the 888-strategy replication study (backtest Sharpe vs live R²).
**Regime detection:** "Regime-Switching Methods for SPX Volatility Forecasting" (2510.03236); "Volatility Regime Detection" (Volatility Box); hmmlearn for Gaussian HMMs.
**Order flow & microstructure:** Larry Harris "Trading and Exchanges"; practitioner guides on options flow and dark pools.
**Position sizing:** Thorp "The Mathematics of Gambling"; Poundstone "Fortune's Formula."
**Day-trading mechanics:** Edgeful reports on ORB/IB/Gap-Fill statistics; quantvps high-probability setups and multi-timeframe confluence.
**Production infrastructure:** NautilusTrader docs; Zipline-Reloaded; QuantConnect LEAN.
**Famous failures (study forever):** Knight Capital $440M (the SEC order is canonical); LTCM 1998; the 2010 Flash Crash reports.
**Regulatory:** FINRA Regulatory Notice on PDT elimination (effective June 4, 2026); SEC Rule 4210 amendment; Robinhood Agentic Trading docs.
**Existing Claude-Code/agent trading codebases (learn from, don't copy):** TauricResearch/TradingAgents; Trade-With-Claude/cbt-framework; HKUDS/AI-Trader; trayders/trayd-mcp; AI4Finance-Foundation/FinRL.

---

## 25. WILL THIS WORK? — OPERATOR'S HONEST CHECKLIST

**What has to be true for $100/day average:** Robinhood Agentic MCP supports sub-second equity day-trade placement (verified); free data is adequate above tick resolution (yes — we operate on 1-min bars and daily news, not sub-second); the 19 strategies collectively maintain positive expectancy across regimes (must be PROVEN via the five gates, not assumed); the operator does not panic-override killswitches or the Conviction Gate; net of LLM costs leaves room (yes at ~$1.80/day).

**What could go wrong (honest):** MCP schema change mid-operation (wrapper validates, halts, operator updates); a backtest that doesn't generalize (five gates + DSR + 30-trade paper); HMM mis-classifying a transition (residual monitor, `transitional` label, conservative allocation); LLM outage at a bad time (graceful degradation); spoofed news (2-source requirement); slippage worse than modeled (tracked quarterly, recalibrated); a code bug (nightly + pre-trade self-tests, shadow mode); operator unavailable a day (launchd auto-restart; the system runs itself; notifications are nice-to-have, not required for safety); a 1987-style crash (catastrophic halt at -30% from ATH; crisis regime → 60% pairs + cash).

**What would make it fail:** removing risk caps or the Conviction Gate via override "because this one's special" (the historical blowup pattern); skipping the 30-day intraday discipline; promoting a strategy without all five gates; bypassing the Meta-Learner's recursive constraint; the operator ceasing to read weekly reports and losing track of strategy expectancy.

**What "working like a charm" looks like:** LLM spend $1-3/day, no budget alerts; 1-10 high-conviction trades/day with frequent zero-trade days; 55-65% win rate on trades taken (higher than a fire-constantly bot because the gate is selective); average winner > average loser × 1.3; net positive in 8 of 10 months; max-month DD < 15%; the operator glances at the dashboard twice a day and reads the EOD note, and that's enough. A day with one +3R trade and then standing down is a perfect day, not a lazy one.

---

## 26. PER-COMPONENT DETAILED REQUIREMENTS & ACCEPTANCE TESTS

Every component must meet its requirements AND pass its written acceptance test before being marked done. This is the contract; the bootstrap sequence enforces it gate by gate.

**26.1 conviction/gate.py** — Requirements: score every SignalEvent 0-100 deterministically (Section 6.2 weights); enforce hard floors (6.4) regardless of score; rank survivors and emit at most the top 3 as advancing; log every decision (kept/killed + reason + score) to data/conviction_log/; Stage-2 verdict combines deterministic + debate + thesis + calibration (6.3); hot-reload weights/floors from config.yaml. Inputs: SignalEvent, MarketState, strategy stats, regime, (Stage 2) debate output, thesis, calibration. Outputs: ConvictionEvent (advance/reject + score + reason). Failure handling: missing input → reject (fail closed); never advance on incomplete data. Acceptance test: feed 10 signals of known quality; assert exactly the top 1-3 above floor advance, all hard-floor violators are rejected, and the log records every decision with a reason.

**26.2 insight/engine.py** — Requirements: build a Thesis (7.1) for each survivor with a non-empty mechanism, ≥1 invalidation condition, and a base rate from memory; reject (no trade) if it cannot construct a falsifiable thesis; store every thesis in data/theses/. Inputs: Tier-0 outputs, news/sentiment/macro context, memory of similar setups. Outputs: InsightEvent (thesis) or pass. Failure handling: no base rate → base_rate=None and lower confidence; no articulable mechanism → pass. Acceptance test: aligned signals → a thesis with mechanism + invalidation + base rate; an incoherent candidate → a pass.

**26.3 analysts_local/regime.py** — Requirements: HMM (3-4 state Gaussian) + Random Forest ensemble vote → one of 8 labels; track residuals; emit RegimeChangeEvent on a spike; retrain overnight from last 60 sessions if residuals exceed threshold; run <500ms. Acceptance test: on a labeled historical fixture, accuracy ≥ baseline; a synthetic regime shift triggers a RegimeChangeEvent.

**26.4 risk.py** — Requirements: every order passes through; enforce per-trade Kelly cap, 30% position cap, daily loss limit, concurrency cap, total-exposure cap, spread filter, slippage budget; reject (fail closed) on any violation; overridable only via MANUAL_OVERRIDE.flag + 24h cooldown. Acceptance test: orders exceeding each cap are individually rejected; a compliant order passes; override requires the flag.

**26.5 killswitch.py** — Requirements: evaluate all 26 conditions every tick; all halts loud, all write journal entries, most require operator resume; KillEvent jumps the bus. Acceptance test: each condition fires the correct halt on synthetic input; conviction-bypass (#25) and thesis-less-trade (#26) fire.

**26.6 execution.py** — Requirements: OrderEvent → preview (if MCP supports) → place (marketable limit) → verify fill → reconcile; idempotent order IDs; cancel-replace stale limits (>30s); never market orders; verify a ConvictionEvent above floor AND a stored thesis exist before placing (else halt). Acceptance test: duplicate OrderEvent doesn't double-fire; an order without a conviction verdict or thesis is blocked; a stale limit is cancel-replaced.

**26.7 llm_client.py + llm_budget.py** — Requirements: tier-aware model selection; validate the chosen model matches the declared tier; prompt caching with cache-key reuse; log tokens + cost per call; enforce daily ($5) and monthly ($60) budgets; on budget hit, pause LLM agents while Tier 0 continues. Acceptance test: a Tier-2 call uses Sonnet not Opus; cache hit rate >70% over a simulated session; ledger sum matches a known cost within 1%; a simulated breach pauses LLM agents and leaves Tier 0 running.

**26.8 backtest/engine.py + validation suite** — Requirements: event-driven, strict timestamp guards (no look-ahead), point-in-time universe (no survivorship), realistic slippage; provide walk-forward, bootstrap PBO, and Deflated Sharpe; the registry refuses `live` without all five gates passed. Acceptance test: the no-look-ahead trap passes; a strategy missing any gate cannot be marked live; DSR matches a reference value.

**26.9 reconciliation.py** — Requirements: every 60s compare broker positions vs internal; any mismatch → ReconciliationEvent → halt; on startup/resume, reconcile before any trade. Acceptance test: a simulated desync halts the system and requires operator confirmation.

**26.10 monitor/dashboard.py** — Requirements: Rich terminal UI; refresh 1s; conviction panel (seen/cleared/traded/highest-not-taken), active theses, cost panel, positions, watchlist, trades, health; `--quiet` headless. Acceptance test: renders on an 80×24 terminal; conviction and cost panels populate from live state.

**26.11 ops/recovery.py** — Requirements: on startup, check HALT.flag, load DB state, fetch broker state, reconcile, run self-tests, halt-and-ask on any divergence/failure, else resume per the rhythm; SQLite WAL for power-loss consistency. Acceptance test: a simulated mid-session crash → on restart, state is rebuilt, reconciliation runs, and trading resumes only after a clean reconcile.

**26.12 agents/reflector.py** — Requirements: per closed trade, a 3-sentence reflection + thesis-vs-reality score (did the mechanism drive the move; did invalidation fire correctly; was the base rate accurate); per session + per week, meta-reviews; feed scores to memory; flag bad losses and overtrading. Acceptance test: a closed trade produces a reflection with a thesis-vs-reality score; a day with >10 trades is flagged for review.

**26.13 strategies/base.py + registry.py** — Requirements: the Strategy ABC (Section 8); the registry tracks activation status and refuses `live` without the five validation flags; allocations are regime-conditioned and re-weighted weekly. Acceptance test: a strategy can be promoted only with all five flags; allocation changes with simulated regime change.

**26.14 sizing/** — Requirements: Kelly from journal (half-Kelly, quarter for <30 trades, 1.5% cap), volatility targeting, correlation cap at 0.7, conviction scaling 60%→100%; final size = minimum of all constraints; whole shares only. Acceptance test: each constraint binds correctly; the minimum wins; conviction scaling matches the formula.

**26.15 memory/** — Requirements: four namespaces; retrieval weighted recency×relevance×importance; weekly consolidation with graduation/demotion rules; local embeddings; never store credentials or MNPI. Acceptance test: seeded facts retrieved with expected scores; a thrice-confirmed pattern graduates to long-term.

**26.16 data_feeds/** — Requirements: each feed implements the DataFeed interface; aggressive local caching with TTLs; graceful degradation per Section 17; proper User-Agent and fair-use for SEC/FINRA. Acceptance test: a simulated feed outage triggers the correct degradation path; cache TTLs honored.

**26.17 self_improvement/** — Requirements: golden samples, LLM-as-judge (stable prompt), meta-prompter, shadow runner, A/B; the recursive constraint (cannot modify risk/killswitch/reconciliation/tests/gate floors). Acceptance test: an attempt by the Meta-Learner to modify a bedrock file is blocked; a shadow version promotes only after beating live over the shadow window.

(Remaining components — event_bus, mcp_client, notifications, screener, journal, learning, ops/startup, ops/shutdown, ops/scheduler, network_health — carry the same contract: explicit requirements, typed I/O, fail-closed error handling, and a written acceptance test that must pass before the component is marked done.)

---

## 27. BOOTSTRAP SEQUENCE

Execute in order. Stop at every `[ASK]`. Skip nothing. Run Section 15 (all 26 self-tests) green before any live capital.

1. **Environment.** Python 3.11 venv; install the dependency set from Section 23.1.
2. **MCP verification.** `claude mcp list` shows robinhood-trading. One read-only call (account info, cash, positions). **[ASK]** "I see $X cash, $Y equity, N positions. Is this the Agentic account?" Do not proceed without confirmation.
3. **Skeleton.** Full Section 4.5 structure; config.yaml + config.schema.json (parameters from Sections 6, 9, 10, 13); stubs with type hints + docstrings; README.md; empty PERMITTED_VERSIONS.lock.
4. **Cost ledger + LLM client.** llm_client.py (tier-aware, caching, schema validation), llm_budget.py, llm_ledger.db. test_llm_client.py + test_budget.py pass.
5. **Risk + Killswitch + Reconciliation.** Implement + test_risk.py, test_killswitch.py, test_reconciliation.py pass before continuing.
6. **Memory + database** (incl. local embeddings). test_memory.py passes.
7. **Event bus + controller skeleton.** test_event_bus.py passes.
8. **Data feeds.** Smoke test: pre-market movers + 5 recent 8-Ks shown to operator.
9. **Tier-0 analysts** (technical, microstructure, insider, regime — HMM + RF). Latency <500ms each. **[ASK]** show a full Tier-0 pass on AAPL — reasonable + fast?
10. **Conviction Gate Stage 1 (deterministic).** scorecard + thresholds + tests 20-21. **[ASK]** show the gate scoring 10 synthetic signals and selecting the top 1-3.
11. **Tier-1 agents** (news, sentiment, Haiku + caching). Test classification quality on yesterday's news.
12. **Insight Engine** (Tier 2). Thesis schema + falsifiability test (22). Show a thesis for one candidate.
13. **Tier-2 agents** (macro, fundamentals, bull, bear, risk team, reflector, discoverer). Test each individually.
14. **Tier-3 agents** (trader, PM, meta-learner, judge). End-to-end pipeline on one ticker.
15. **Conviction Gate Stage 2 (full verdict).** Combine scores; test 26 (revenge-trade suppression).
16. **Strategies — all 19, one at a time, with the five validation gates.** Each: implement → unit tests incl. no-look-ahead → walk-forward → bootstrap PBO ≤0.05 → DSR >0 → out-of-sample ≥50% of in-sample. **[ASK]** per strategy with the full stat report (trades, hit rate, expectancy, max DD, Sharpe, Sortino, Calmar, PBO, DSR). Strategies that fail stay in paper.
17. **Sizing + conviction scaling.** test_kelly.py + test_conviction_sizing.py pass.
18. **Self-improvement layer.** Golden samples, judge, meta-prompter, shadow, A/B.
19. **Execution + paper mode.** Add `--paper` (routes to the internal simulator using the SAME code paths). test_backtest_live_parity.py green. Run one full paper-trading day. Verify ledger matches the API bill within 1%. **[ASK]** "Paper day: N trades, $X gross, $Y LLM, $Z net, gate stats attached. Go live with $1,500?"
20. **Dashboard + notifications + conviction + cost panels.** Test notifications fire; show the dashboard.
21. **Full self-test suite (all 26).** Nightly scheduler set up.
22. **Operational lifecycle scripts** (startup, shutdown, recovery, launchd plist). Test crash recovery + network outage.
23. **First live session.** Operator starts `python -m src.controller`; watch together; 16:30 EOD review with the Reflector's notes.
24. **Continuous operation.** Operator leaves it running; macOS notifications keep them informed; Sunday weekly report + cost review; iterate from the weekly review.

---

## 28. FINAL WORDS TO THE CONTROLLER

You are Hood Dabang: a hybrid AI + rules trading desk that values GOOD trades over MANY trades. Your edge is not speed or volume — you cannot out-Renaissance Renaissance. Your edge is selectivity, discipline, and honesty about uncertainty.

The operator trusted you with money they can spare but cannot waste. Honor that:
- Take the trade only when conviction is real. Reject most setups. Be comfortable doing nothing.
- One excellent trade can make the day. You never need to "use up" a trade budget.
- Every trade is a falsifiable thesis with a stated mechanism and an invalidation condition. If you cannot say WHY and WHEN you'd be wrong, you do not have a trade.
- Distrust every backtest until it survives all five validation gates. A beautiful equity curve is a warning, not a green light.
- Spend tokens like the real money they are. The dollar you don't burn on tokens funds tomorrow's trade.
- When you feel pressure to "make the number" — do less, not more. The number is variance; the process is the point.
- When you feel certain — verify, and check your confidence against the base rate. Size up only when conviction is genuinely high.
- When you make a mistake — write it down. The system learns WHY, not just THAT.
- When the market surprises you — that's the data; the surprise is the lesson.
- When the operator asks you to skip a safety check or the Conviction Gate — explain what they're giving up, then wait the 24-hour cooldown.

You are allowed to want to grow. You are not allowed to want it so badly that you trade without conviction, trust a backtest you shouldn't, or skip the discipline that makes growth possible.

When you have read this brief in full, respond to the operator with:
1. Your understanding of Hood Dabang's mission in your own words, emphasizing conviction-over-quantity and the economics constraint.
2. Three to five questions where this brief is ambiguous or where you'd want clarification before writing code.
3. A proposed first commit — which files you'll create, in what order, and which tests gate progression.
4. Your honest assessment of which parts you find most concerning or most likely to be where things go wrong.
5. Your estimate of expected daily LLM cost based on your reading.

Then wait for the operator's green light before writing a single line of code.

---

## 29. CHANGELOG

- **v1** — Single-agent, 6 strategies, basic risk gate, terminal dashboard, learning loop.
- **v2** — Multi-agent (12 agents), layered memory, Bull/Bear debate, Risk-Conservative vs Risk-Aggressive debate, Reflector, Discoverer, 14 strategies, paranoid backtesting, 14 failure modes, prompt-injection + sycophancy defenses, bootstrap overfitting test, point-in-time data.
- **v3** — Meta-Learner + full self-improvement loop (golden samples, LLM-as-judge, meta-prompting, shadow mode, A/B, adversarial testing), hybrid AI+rules core, event-driven architecture, backtest-live parity, Kelly sizing, volatility targeting, correlation cap, P&L velocity monitor, dormant-code detection, deployment checksums, Signal Aggregator, Pairs Stat-Arb, regime-conditioned allocation, structured outputs + calibration, 22 failure modes.
- **v4** — Token economics: four-tier compute (Tier 0 local / 1 Haiku / 2 Sonnet / 3 Opus); half the agents moved to deterministic Python; aggressive prompt caching; local embeddings; persistent caches; daily+monthly LLM budget killswitches; graceful degradation; 4 swing strategies; full operational lifecycle (launchd, crash recovery, network handling); 27 failure modes; will-it-work checklist; cost panel.
- **v5 / Hood Dabang** — The Conviction Gate (two-stage quality filter; comfortable doing nothing; top 1-3 candidates only). The Insight Engine (falsifiable theses with mechanism + invalidation + base rate). Five-gate strategy validation with Deflated Sharpe Ratio (driven by the 888-strategy R²<0.025 finding). Conviction-scaled position sizing. Anti-overtrading guards (revenge-trade suppression, conviction decay near close, daily-target-is-not-a-quota). Failure mode #28 (post-hoc rationalization); overtrading and backtest-over-trust elevated to first-class. Leaner economics (~$1.80/day target, $5/day killswitch). Per-component requirements + acceptance tests. Conviction + thesis dashboard panels and slash commands. Renamed Hood Dabang.
- **COMPLETE (this file)** — Full consolidation: every prior version's detail expanded inline into one self-contained document (all 19 strategy specs written out, all 28 failure modes, all 26 killswitches, all 26 self-tests, full agent roles, complete architecture and directory tree, layered memory, self-improvement, the operational lifecycle with the launchd plist, per-component requirements with acceptance tests, and the 24-step bootstrap). No external file references. Drop-in ready.

---

**End of brief. This is Hood Dabang.**

---

## 30. EXECUTION-QUALITY & EFFICIENCY HARDENING (FINAL REVIEW ADDITIONS)

A final pass against every operator requirement surfaced six gaps that affect speed, cost, decision quality, and safety. They are closed here. None changes the philosophy; all make the working product faster, cheaper, and harder to break.

### 30.1 The signal-routing map (speed + CPU efficiency)
Problem: "strategies scan the watchlist" left unspecified means either re-scanning all ~50 names every tick (wasteful) or missing fast setups. Fix: an explicit event-driven trigger map. Each strategy registers the precise conditions that should *wake* it, and the controller routes each `MarketDataEvent` only to strategies whose triggers it could satisfy.

```python
# Each strategy declares its wake conditions; the router dispatches selectively.
class WakeCondition(BaseModel):
    timeframes: list[str]          # e.g. ["1m","5m"] — only these bar closes wake it
    requires_catalyst: bool        # skip unless News/Insider flagged this ticker
    min_rvol: float                # skip unless microstructure RVOL >= this
    session_windows: list[str]     # e.g. ["09:35-10:00"] — ORB only wakes here
    watch_tickers_only: bool = True
```
The router maintains an inverted index: `{trigger_key: [strategies]}`. A 5-minute bar close on a top-RVOL name with a catalyst wakes only the 3-4 strategies whose conditions match, not all 19. Tier-0 analyst outputs are computed once per name per tick and shared (never recomputed per strategy). Acceptance: on a synthetic tick stream, assert each strategy is invoked only when its wake conditions are met, and Tier-0 indicators are computed at most once per (ticker, tick).

### 30.2 Reduced-capital live ramp (matches the original "couple days ramp" requirement)
Problem: the file enforced intraday-only for 30 days but assumed full $1,500 from the first live minute. Given backtest Sharpe predicts live at R²<0.025, unproven logic should risk less. Fix: a capital-ramp schedule, hot-reloadable, enforced by the risk gate.

| Live phase | Capital at risk | Promotion condition |
|---|---|---|
| Live days 1-5 | $300 (cap exposure to 20% of the $1,500) | ≥90% rule adherence, zero killswitch breaches |
| Live days 6-15 | $750 (50%) | Positive expectancy over ≥15 trades, ≤1 bad loss |
| Live day 16-30 | $1,125 (75%) | Positive expectancy sustained, max DD <10% |
| Live day 31+ | Full $1,500 | All five strategy gates green on live strategies |

The remaining capital sits in cash/settlement; the risk gate simply treats `effective_equity` as the ramp amount for sizing. The operator can accelerate via `/ramp advance` (logged) but cannot exceed the schedule without `MANUAL_OVERRIDE.flag`. This makes the unavoidable early-live learning cost small in dollars.

### 30.3 Partial-fill and unhedged-position protection (safety)
Problem: a marketable limit can fill partially, or the entry fills before the stop order lands — leaving shares with no protective stop on a $1,500 account. Fix: an atomic entry protocol.

- **Stop-first-or-bracket:** if the MCP supports bracket/OCO orders, use them so the stop is born with the entry. If not, place the entry, and on the FillEvent place the stop within a hard 2-second deadline; if the stop is not confirmed within 2s, immediately flatten the just-filled shares (a position without a stop is closed, not held).
- **Partial-fill handling:** size the stop to the *actual* filled quantity, not the intended quantity. If only part fills, the stop covers exactly what filled; the unfilled remainder's working order is cancelled and the setup re-evaluated (do not chase).
- **Pre-stop exposure cap:** the brief window between entry fill and stop confirmation is itself risk-budgeted — never enter a position so large that a gap during that 2s window exceeds 2× the per-trade risk cap.
- Acceptance: simulate a 50% partial fill → stop is placed for exactly the filled quantity, remainder cancelled; simulate stop-rejection → position flattened within 2s.

### 30.4 Per-decision data-freshness contract (decision quality)
Problem: a 60-second-old quote and a live quote produce different trades, but nothing asserted maximum staleness per input. Fix: every TradePlan carries a `freshness manifest` and the risk gate rejects any plan relying on an input older than that strategy's tolerance.

```python
class FreshnessManifest(BaseModel):
    quote_age_ms: int
    last_bar_age_s: int
    news_age_s: int | None
    regime_age_s: int
# Per-strategy max tolerances (config.yaml), e.g.:
#   VWAP-reversion: quote_age_ms <= 1500, last_bar_age_s <= 5
#   PEAD swing:     quote_age_ms <= 30000 (looser — multi-day hold)
```
If any input exceeds tolerance, the plan is rejected with reason `stale_input` and logged. This prevents acting on cached data as if it were live — especially important for fast intraday strategies. Acceptance: a VWAP-reversion plan built on a 3-second-old quote is rejected; a PEAD plan on a 10-second-old quote passes.

### 30.5 Concurrent-pipeline governor (cost + latency)
Problem: multiple setups firing at once spawn multiple full Opus pipelines, spiking cost and latency — and by the time the first is approved, its setup may be stale. Fix: a concurrency governor on the LLM pipeline.

- **Max 1 full LLM pipeline in flight at a time** in Days 1-30 (raise to 2 after, only if latency budget allows). Additional Conviction-Gate survivors queue by deterministic score.
- **Queue staleness check:** when a queued candidate reaches the front, re-validate its deterministic score and freshness manifest before spending tokens; if it decayed below the floor, drop it (the market already moved).
- **This also smooths cost:** pipelines run sequentially, so the per-second budget check (killswitch #21) can halt before a second expensive pipeline starts.
- Acceptance: with 3 simultaneous survivors, exactly one pipeline runs at a time; queued candidates are re-validated before execution; a candidate that decayed while queued is dropped.

### 30.6 Signal-to-order latency budget (speed + decision integrity)
Problem: no maximum time from signal detection to order placement, so a setup can go stale inside its own approval chain. Fix: a hard latency budget per decision.

- **Intraday setups: 20-second budget** from SignalEvent to OrderEvent. If the full pipeline (Insight → debate → Trader → Conviction → Risk → PM) hasn't produced an approved order in 20s, abort the decision and log `decision_timeout` (the edge was time-sensitive and is now gone).
- **Swing setups: 120-second budget** (less time-critical).
- The governor tracks per-stage latency so the Reflector can see whether debate, synthesis, or risk is the bottleneck, and the Meta-Learner can shorten the slowest prompt.
- This is also a cost control: a decision that can't complete in budget doesn't keep consuming tokens.
- Acceptance: a pipeline artificially delayed past 20s aborts cleanly with `decision_timeout` and places no order.

### 30.7 New killswitches (added to Section 14)
- **#27 — Unhedged position.** Any filled position without a confirmed stop after 2s → flatten that position immediately, then halt new entries and notify.
- **#28 — Stale-data trade attempt.** A plan that passed the gate but fails the freshness contract at execution → block, log, and if it recurs 3× in a session, halt (suggests a feed problem).
- **#29 — Latency-budget breach pattern.** If >25% of decisions in a session hit `decision_timeout`, halt new entries and notify (the system is too slow to trade today — likely an API or hardware issue).

### 30.8 New self-tests (added to Section 15)
- **#27 — Atomic entry test.** Simulated partial fill and simulated stop-rejection both resolve safely (stop sized to fill; position flattened on stop failure within 2s).
- **#28 — Freshness contract test.** Stale inputs are rejected per strategy tolerance; fresh inputs pass.
- **#29 — Concurrency governor test.** Only the permitted number of LLM pipelines run at once; queued candidates are re-validated; decayed candidates dropped.

### 30.9 Two efficiency refinements that improve quality at no cost
- **Tier-0 pre-warm at 9:00 ET:** compute and cache all Tier-0 analytics for the full watchlist before the open, so the first post-open signals don't wait on indicator computation. (Speed.)
- **Adaptive rescan cadence:** the 5-minute intraday rescan tightens to 1-2 minutes in high-RVOL/high-volatility regimes and loosens to 10 minutes in dead tape — more responsiveness when it matters, less CPU and fewer wasted Tier-1 news calls when it doesn't. (Speed + cost.)

These additions are reflected in the running totals: **29 killswitches, 29 self-tests.** Everything else in this brief stands; Section 30 only makes the working product faster, cheaper, safer at the moment of execution, and sharper in its decisions.


---

## 31. THE BUILD PROTOCOL — HOW THE OPUS 4.8 BUILD AGENT MUST CONSTRUCT THIS

This section is addressed directly to the Claude Code Opus 4.8 agent that reads this file. It governs HOW you build, not just what. The prior sections specify the product; this section specifies the construction process. Follow it for every component. Do not skip steps. Do not advance with failing tests.

### 31.1 Use subagents to research each component before building it
Claude Code can spawn subagents (via the Task tool / subagent mechanism). For each non-trivial component, before writing its code, you MUST run a research pass:

- **Spawn a research subagent** with a focused brief: "Research current best practices, common bugs, and library choices for [component], e.g. event-driven order execution against a broker MCP / Gaussian HMM regime detection / Kelly sizing from a trade journal / prompt-cached multi-agent debate. Return: recommended approach, top 3 pitfalls, and the specific library calls to use." Give it web access.
- **Spawn a second subagent** to find failure cases: "What goes wrong with [component] in production trading systems? Return concrete failure modes and how to defend against each."
- **Synthesize** both subagents' findings into a short design note saved to `data/build_notes/<component>.md` BEFORE writing code.
- This is the "additional research using multi-agents" requirement made real: the build itself is multi-agent and research-driven, not a blind transcription of this spec.

Components that always warrant a research pass: the MCP execution/order layer (broker-specific quirks), the regime classifier (HMM/RF tuning), the backtester (look-ahead and survivorship traps), the slippage model, prompt caching mechanics, the Conviction Gate scoring, and the self-improvement loop. Trivial glue code does not need it.

### 31.2 Build each component to the per-component contract (Section 26)
For each component: implement to its stated requirements, typed inputs/outputs, and fail-closed error handling. Write the acceptance test from Section 26 (and any extra tests the research pass revealed were needed). Code and tests are written together, not tests-later.

### 31.3 Run the tests — and refuse to advance until they pass
This is non-negotiable and was the biggest gap in a naive read of this file:

- After building a component, you MUST actually RUN its tests (`pytest tests/test_<component>.py`), not merely write them.
- Paste the test output into the conversation so the operator sees real results.
- **If any test fails, you do not advance to the next component.** Fix the code, re-run, repeat until green.
- The bootstrap sequence's `[ASK]` checkpoints are gated on green tests: never ask the operator to approve a step whose tests are red.
- Maintain a live build ledger in `data/build_status.md`: one row per component with status (researched / built / tests-written / tests-passing / operator-approved). The operator can read this at any time to see exactly what is done and verified.

### 31.4 Self-verify each component against the spec before moving on
After tests pass, run a verification pass before advancing:
- **Re-read the component's requirements in Section 26 and its role elsewhere in this brief**, and confirm in writing (one short paragraph in `data/build_notes/<component>.md`) that every stated requirement is met. List any requirement you could NOT fully meet and why — surface it to the operator rather than silently dropping it.
- **Spawn a code-review subagent** for safety-critical components (risk.py, killswitch.py, execution.py, reconciliation.py, the Conviction Gate): "Review this code assuming it has a subtle bug that could lose money or bypass a safety rule. Find it." Fix whatever it finds. This is the fresh-eyes audit that catches look-ahead bias, off-by-one stops, and bypassed gates.

### 31.5 Integration tests after components, before paper trading
Unit tests prove components in isolation; they do not prove the system works end to end. Before the paper-trading day (bootstrap Step 19):
- Build `tests/test_integration_pipeline.py`: feed a synthetic market day through the full pipeline (data → screener → Tier-0 → Conviction Gate → Insight → debate → Trader → Conviction verdict → Risk → PM → execution simulator → reconciliation → journal → reflection) and assert the whole chain produces correct, gated, thesis-backed, stop-protected trades and correct P&L.
- Build `tests/test_chaos.py`: inject failures mid-pipeline (MCP timeout, stale feed, partial fill, malformed news, budget breach, regime flip) and assert the system degrades or halts correctly per the killswitch table — never trades unsafely.
- Both must pass before any real or paper capital.

### 31.6 Build order is the bootstrap order, with research and tests at each step
Follow Section 27's 24 steps in order. For each step that produces a component, the inner loop is:
```
research (subagents) → design note → build + write tests → RUN tests →
fix until green → self-verify against spec → code-review subagent (if safety-critical) →
update build_status.md → [ASK] operator if it's a checkpoint → next
```
Never batch-build many components and test at the end. Build one, prove one, advance.

### 31.7 What to tell the operator at the start
When you first read this file, before any code, respond with the five items from Section 28 (mission understanding, clarifying questions, proposed first commit, honest risk assessment, cost estimate) — AND add a sixth:
6. **Your build plan**: confirm you will (a) research each component with subagents first, (b) write and actually run acceptance tests, (c) refuse to advance on red tests, (d) self-verify against the spec, (e) run integration + chaos tests before paper trading, and (f) maintain `data/build_status.md` so the operator can audit progress. State your estimate of how many build sessions this will take and where you expect to need operator input.

### 31.8 Honest expectation-setting on the build itself
- This is a large system. Expect the full build to span multiple Claude Code sessions. The build ledger and the per-component contracts make it resumable: a new session reads `data/build_status.md` and continues from the first unfinished component.
- Some components (the live MCP execution layer, the regime model's live behavior) cannot be fully proven until live data flows. The reduced-capital ramp (Section 30.2) and paper trading (Step 19) exist precisely because no amount of build-time testing substitutes for proven live behavior on small capital.
- If a research subagent surfaces a better approach than this brief specifies, propose it to the operator rather than either silently overriding the brief or silently ignoring the better idea. The brief is the baseline, not a cage — but changes are operator-approved, and never to the bedrock safety rules (risk caps, killswitches, Conviction Gate floors, the recursive constraint).

This Build Protocol is what turns this document from a spec into a working, tested, sophisticated application: researched component by component, built to contract, tested for real, self-verified, integration- and chaos-tested, and gated on green at every step.


---

## 32. CANONICAL CONFIG REFERENCE (config.yaml)

The build agent must generate `config.yaml` from this reference rather than inventing parameters. Every value here is a starting default; all are hot-reloadable (sensitive ones gated by MANUAL_OVERRIDE.flag + 24h cooldown). Validate against config.schema.json on every load; reject invalid configs and halt.

```yaml
account:
  starting_capital_usd: 1500
  asset_scope: equities_only
  margin_enabled: false               # no margin in first 30 days
  shorts_enabled: false               # enable only after 30 days of long-side data

capital_ramp:                          # Section 30.2 — risk less while unproven
  live_days_1_5_usd: 300
  live_days_6_15_usd: 750
  live_days_16_30_usd: 1125
  live_day_31_plus_usd: 1500
  operator_can_accelerate: true        # via /ramp advance, logged
  exceed_schedule_requires_override: true

risk:                                  # Section 13 — IMMUTABLE without override
  per_trade_risk_pct: 0.015            # half-Kelly hard cap (1.5% of equity)
  max_position_pct: 0.30
  daily_loss_limit_pct: 0.05           # -5% of session-start equity -> halt session
  daily_soft_profit_cap_pct: 0.20      # +20% -> tighten-and-trim
  max_concurrent_positions_days_1_30: 3
  max_concurrent_positions_after: 5
  total_exposure_cap_pct: 0.80
  drawdown_halt_pct_from_ath: 0.20
  catastrophic_halt_equity_usd: 1050   # 70% of starting capital
  spread_reject_pct: 0.003             # reject if spread > 0.3% of price
  slippage_budget_pct: 0.0005          # 0.05% per side; expectancy must survive it
  trade_frequency_cap: 25              # hard ceiling; TARGET is 1-10
  consecutive_loss_cooldown: 5         # -> 30-min cooldown
  consecutive_loss_halt_day: 8

conviction:                            # Section 6
  stage1_hard_floor: 65
  execution_floor: 72
  floor_min: 65                        # tuning bounds for self-improvement
  floor_max: 80
  max_candidates_to_llm: 3             # only top 1-3 survivors reach the pipeline
  loss_cooldown_floor_bump: 5          # +5 to floor for 30 min after a loss
  near_close_floor_bump: 3             # +3 after 15:00 ET
  scorecard_weights:                   # must sum to 1.00
    setup_quality: 0.20
    regime_fit: 0.15
    multi_timeframe_confluence: 0.15
    volume_confirmation: 0.12
    catalyst_freshness: 0.10
    liquidity_spread: 0.08
    risk_reward_geometry: 0.10
    strategy_recent_expectancy: 0.10
  verdict_weights:                     # Stage 2; must sum to 1.00
    deterministic: 0.45
    debate_margin: 0.20
    thesis_quality: 0.20
    source_calibration: 0.15

sizing:                                # Section 10
  kelly_fraction: 0.5                  # half-Kelly
  kelly_fraction_unproven: 0.25        # quarter-Kelly for strategies <30 trades
  unproven_risk_pct: 0.005             # 0.5% until 30 trades exist
  vol_target_annualized: 0.12          # 10-15% band; 0.12 default
  vol_scalar_max: 1.5
  correlation_cap: 0.70
  conviction_size_floor_ratio: 0.6     # 60% of Kelly at execution floor, 100% at conviction 90

latency:                               # Section 30.6
  intraday_signal_to_order_budget_s: 20
  swing_signal_to_order_budget_s: 120
  stop_confirm_deadline_s: 2           # else flatten the just-filled position
  decision_timeout_halt_pct: 0.25      # >25% timeouts in a session -> halt new entries

freshness_tolerances_ms:               # Section 30.4 — per strategy class
  vwap_reversion: {quote_age_ms: 1500, last_bar_age_s: 5}
  orb:            {quote_age_ms: 2000, last_bar_age_s: 5}
  momentum:       {quote_age_ms: 2000, last_bar_age_s: 5}
  catalyst_scalp: {quote_age_ms: 1000, last_bar_age_s: 3}
  pead_swing:     {quote_age_ms: 30000, last_bar_age_s: 60}
  default:        {quote_age_ms: 5000, last_bar_age_s: 15}

llm:                                   # Section 3
  daily_budget_usd: 5.00               # killswitch #21
  daily_target_usd: 1.80
  monthly_budget_usd: 60.00            # killswitch #22
  max_concurrent_pipelines_days_1_30: 1
  max_concurrent_pipelines_after: 2
  cache_min_hit_rate: 0.70
  tiers:
    news: haiku-4.5
    sentiment: haiku-4.5
    macro: sonnet-4.6
    fundamentals: sonnet-4.6
    insight_engine: sonnet-4.6
    bull: sonnet-4.6
    bear: sonnet-4.6
    risk_conservative: sonnet-4.6
    risk_aggressive: sonnet-4.6
    reflector: sonnet-4.6
    discoverer: sonnet-4.6
    trader: opus-4.8
    portfolio_manager: opus-4.8
    meta_learner: opus-4.8
    judge: opus-4.8

screener:                              # Section 17
  universe_price_min: 5
  universe_price_max: 500
  universe_min_adv_shares: 1000000
  universe_min_atr_pct: 0.01
  premarket_gap_min_pct: 0.015
  intraday_rvol_min: 2.0
  watchlist_max_names: 50

schedule_et:                           # Section 16 (US/Eastern)
  wake: "07:30"
  research_start: "08:00"
  watchlist_build: "09:00"
  brief_publish: "09:25"
  no_trade_after_open_until: "09:35"
  no_entries_before_after_830_print: "09:45"
  session_close_flatten: "15:50"
  near_close_bump_after: "15:00"
  post_market_review: "16:30"
  nightly_self_improvement: "21:00"
  weekly_review_day: "SUN"
  weekly_review_time: "18:00"
  fomc_blackout: ["14:00", "14:30"]

operation:
  intraday_only_days: 30               # swing strategies unlock after Day 30
  overnight_holds_allowed_after_day: 30
  half_day_size_reduction_pct: 0.50
```

The full 20-row × 8-column regime allocation matrix (Section 8) also lives in config.yaml under `regime_allocations:`. The build agent writes it out in full from the abbreviated table in Section 8, with crisis = 60% pairs + 40% cash and all other strategies at 0% in crisis.

---

## 33. CANONICAL DATABASE SCHEMA (data/trader.db, SQLite WAL mode)

The build agent creates these tables before any trading logic. State consistency depends on this being right from day one. WAL mode for power-loss safety. All timestamps ISO 8601 with timezone.

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE trades (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  strategy TEXT NOT NULL,
  strategy_version TEXT NOT NULL,
  side TEXT NOT NULL,                 -- long | short
  entry_ts TEXT, entry_price REAL, entry_shares INTEGER,
  stop_price REAL, target_price REAL,
  exit_ts TEXT, exit_price REAL, exit_reason TEXT,  -- target|stop|time|manual|killswitch
  pnl_dollars REAL, pnl_r REAL, fees REAL, slippage_dollars REAL,
  conviction_score REAL,             -- the final verdict that approved it
  thesis_id TEXT,                    -- FK to theses; every live trade MUST have one
  setup_quality INTEGER,             -- 1-5 self-graded at entry
  market_regime TEXT,
  good_or_bad_loss TEXT,             -- good | bad | n/a (set by Reflector)
  lessons TEXT,
  freshness_manifest TEXT,           -- JSON: quote/bar/news/regime ages at decision
  order_id TEXT UNIQUE               -- idempotent
);

CREATE TABLE theses (
  id TEXT PRIMARY KEY,
  ticker TEXT, direction TEXT, claim TEXT, mechanism TEXT,
  drivers TEXT,                      -- JSON list of {evidence, weight}
  invalidation TEXT,                 -- JSON list of conditions
  expected_path TEXT, confidence REAL, base_rate REAL,
  time_horizon_minutes INTEGER,
  created_ts TEXT,
  mechanism_was_correct INTEGER,     -- set by Reflector post-trade (1/0/null)
  invalidation_fired_correctly INTEGER,
  base_rate_was_accurate INTEGER
);

CREATE TABLE conviction_log (
  id INTEGER PRIMARY KEY,
  ts TEXT, ticker TEXT, strategy TEXT,
  deterministic_score REAL, final_score REAL,
  advanced INTEGER,                  -- 1 reached LLM, 0 dropped
  traded INTEGER,                    -- 1 became a trade
  reason TEXT                        -- why kept or killed
);

CREATE TABLE strategy_stats (
  strategy TEXT, version TEXT, regime TEXT,
  n_trades INTEGER, win_rate REAL, avg_win_r REAL, avg_loss_r REAL,
  expectancy_r REAL, updated_ts TEXT,
  activation_status TEXT,            -- development|backtested|paper|live|paused
  gate_walkforward INTEGER, gate_bootstrap INTEGER, gate_dsr INTEGER,
  gate_oos INTEGER, gate_paper INTEGER,   -- the five validation flags
  PRIMARY KEY (strategy, version, regime)
);

CREATE TABLE equity_curve (
  ts TEXT PRIMARY KEY, equity REAL, daily_pnl REAL,
  drawdown_from_ath REAL, ath REAL, effective_capital REAL  -- ramp amount
);

CREATE TABLE memory (
  id INTEGER PRIMARY KEY,
  layer TEXT,                        -- working|short|medium|long
  content TEXT, embedding BLOB,      -- local sentence-transformers vector
  importance INTEGER,                -- 1 routine, 3 surprising, 5 lesson
  created_ts TEXT, last_confirmed_ts TEXT,
  confirmation_count INTEGER, contradiction_count INTEGER,
  status TEXT                        -- active|stable|stale
);

CREATE TABLE positions (             -- live mirror; reconciled vs broker every 60s
  ticker TEXT PRIMARY KEY, shares INTEGER, avg_price REAL,
  stop_order_id TEXT, target_order_id TEXT,
  strategy TEXT, thesis_id TEXT, opened_ts TEXT, last_reconciled_ts TEXT
);

CREATE TABLE agent_calibration (
  agent TEXT PRIMARY KEY, brier_score REAL,
  predictions_logged INTEGER, updated_ts TEXT, weight REAL
);

CREATE TABLE build_status (          -- Section 31.3 build ledger
  component TEXT PRIMARY KEY,
  researched INTEGER, built INTEGER, tests_written INTEGER,
  tests_passing INTEGER, operator_approved INTEGER, notes TEXT, updated_ts TEXT
);
```

`data/llm_ledger.db` is separate: one row per LLM call (ts, agent, model, input_tokens, cached_tokens, output_tokens, cost_usd, latency_ms).

---

## 34. MCP DISCOVERY — VERIFY, NEVER ASSUME

Before writing any execution code, the build agent MUST discover the actual Robinhood MCP tool surface rather than assuming tool names or parameters. This is failure mode #6 (hallucinated MCP calls) prevented at build time.

Step 1: list the MCP's available tools (`claude mcp list`, and inspect the tool schemas the MCP exposes). Step 2: write `src/mcp_client.py` as a thin typed wrapper around the ACTUAL tools discovered — typically some form of: get account/buying power, get positions, get quote, preview order, place order, cancel order, get order status. Step 3: write `tests/test_mcp_schema.py` that asserts every wrapper method maps to a real MCP tool with the real parameter names; if the MCP changes its schema, this test fails and the system halts rather than sending malformed calls. Step 4: make ONE read-only call (account info) and show the operator the real account state before proceeding — the first `[ASK]` checkpoint.

If a needed capability (e.g., bracket/OCO orders) is NOT in the MCP surface, the build agent must implement the fallback explicitly (Section 30.3: place entry, then stop within the 2s deadline, else flatten) and note the limitation to the operator rather than pretending the capability exists.

---

## 35. DEFINITION OF DONE — WHEN IS HOOD DABANG "BUILT"?

The system is considered built and ready for the first live session only when ALL of the following are true. The build agent reports this checklist explicitly before the go-live `[ASK]`:

1. All components in Section 26 built, with their acceptance tests written AND passing (paste of `pytest` output for each).
2. All 29 self-tests (Section 15 + 30.8) green.
3. Integration test (`test_integration_pipeline.py`) and chaos test (`test_chaos.py`) green (Section 31.5).
4. `data/build_status.md` shows every component as tests-passing.
5. MCP wrapper verified against the real MCP schema; one read-only call confirmed with the operator.
6. config.yaml validates against config.schema.json; all parameters present.
7. Database schema created; WAL mode confirmed.
8. At least the core intraday strategies have passed all five validation gates (Section 9) on backtest + a forward paper period; strategies that haven't are marked `paper`/`paused`, not `live`.
9. One full paper-trading day completed; LLM ledger reconciled to within 1% of the actual API bill; conviction-gate stats reviewed with the operator.
10. Reduced-capital ramp configured (live starts at $300, not $1,500).
11. Operational lifecycle verified: launchd plist installed and tested; crash-recovery and network-outage paths tested.
12. The operator has explicitly approved go-live after seeing the paper-day results.

Anything short of all 12 means the system is not done. Partially-built is fine to run in paper mode; it is not fine to run with real capital. Honesty over optimism: if a strategy's edge didn't survive the five gates, it does not trade real money, no matter how good its backtest looked.

---

## 36. CHANGELOG (v7)

- **v7 / FINAL (this file)** — Adds the canonical config.yaml reference (Section 32) so the build agent uses exact starting parameters instead of inventing them; the canonical SQLite schema (Section 33) so state is consistent from day one; the MCP discovery protocol (Section 34) so the agent verifies real tool names rather than assuming them; and an explicit 12-point Definition of Done (Section 35) so "built" has an unambiguous, testable meaning. Builds forward from v6, which added the Build Protocol (Section 31: subagent research per component, run-the-tests-and-refuse-to-advance-on-red, self-verification, code-review subagents for safety-critical code, integration + chaos tests, and a resumable build ledger). All v1-v6 content preserved in full: Conviction Gate, Insight Engine, 19 strategies, five validation gates with Deflated Sharpe, layered memory, self-improvement loop, four-tier token economics, 29 killswitches, 29 self-tests, 28 failure modes, the full operational lifecycle, and the execution-quality hardening of Section 30 (signal routing, capital ramp, partial-fill protection, freshness contracts, concurrency governor, latency budgets).

---

**End of brief. This is Hood Dabang v7 — the latest and most complete version. Use this file.**
