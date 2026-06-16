# HOOD DaBang — Go-Live Runbook
**Date prepared:** 2026-06-15  
**State:** Real Robinhood Agentic MCP connected · $1,000 funded · paper/research only  
**Account:** 581853207 (cash, agentic_allowed=true, no margin, no options)  
**Deployment cap:** $500 max deployed (50% of balance) · passcode: "pinappleexpress9"

> This is a planning and operational document only. No code is modified here.
> All file references are to `/Users/alarkpatel/CLAUDE_MASTER/hood-dabang/`.

---

## PRIORITY 0 — Before Any Session (Do These Now, They Are Pre-Conditions)

### 0A. Opt out of maximum Robinhood data sharing
**What:** Email `privacy@robinhood.com` with subject "Limit Sharing" requesting: (1) do not share creditworthiness information with affiliates, (2) do not allow affiliates to market to you. Also email `support@robinhood.com` with subject "Rule 14b-1(c) objection" to prevent disclosure of your holdings to the issuers of securities you own. Visit `https://robinhood.com/us/en/support/articles/data-sharing-preferences/` to disable third-party advertising partner sharing.

**Why:** The Financial Privacy Notice "Agentic Trading" provision (INSIGHTS.md §3) states that NPI — account balances, positions, transaction data — shared with AI providers is not subject to Robinhood's privacy commitments, and revoking AI access does not require the AI provider to delete it. Reducing Robinhood's own lateral sharing of your data reduces the total data footprint before you add the AI-layer exposure on top.

**App mapping:** No code change; this is operator action at Robinhood.

---

### 0B. Review and save a timestamped copy of all 7 legal documents
**What:** The copies already in `/Users/alarkpatel/CLAUDE_MASTER/robinhood-legal/` were reviewed on 2026-06-15. Set a quarterly calendar reminder to re-download and diff them. Robinhood may amend Section 29.8 without notice (Customer Agreement §37.7).

**Why:** INSIGHTS.md §8 Priority 2d — if terms change materially (new AI restrictions, new liability language), you need to know before your next session, not after.

---

## PRIORITY 1 — MCP Client/Adapter: Rebind to the Real Tool Surface

### Step 1: Run tool discovery and validate the tool map
**What:** Start an authenticated HTTP session via `HttpMCPTransport` (`src/mcp_http.py`) and call `client.discover()` followed by `client.validate_tool_map()` (`src/mcp_client.py` lines 117–125). The real Robinhood Agentic MCP exposes these tool names (confirmed from live inspection):

| Logical operation | REAL tool name |
|---|---|
| Get accounts | `get_accounts` |
| Get portfolio / buying power | `get_portfolio` |
| Get positions | `get_equity_positions` |
| Get quote | `get_equity_quotes` |
| Check tradability | `get_equity_tradability` |
| Get OHLCV bars | `get_equity_historicals` |
| Get open orders | `get_equity_orders` |
| Search tickers | `search` |
| Preview order (safe, no fill) | `review_equity_order` |
| Place real order | `place_equity_order` |
| Cancel order | `cancel_equity_order` |
| Get indexes | `get_indexes` |
| Get index quotes | `get_index_quotes` |

**Why:** `DEFAULT_TOOL_MAP` in `src/mcp_client.py` (lines 42–52) uses placeholder names (`get_account_info`, `place_order`, `place_stop_order`, etc.) that do NOT match the real server. `validate_tool_map()` will return every one of them as missing, and the app will halt per the §34 verification requirement. The entire tool-name mapping must be replaced before any live order is possible.

**New code needed:**
- Update `DEFAULT_TOOL_MAP` in `src/mcp_client.py` to match the table above.
- Rename `client.place_stop_order()` to use `place_equity_order` with `type="stop_market"` or `type="stop_limit"` — stops are NOT a separate MCP tool; they are `place_equity_order` with the appropriate type parameter.
- Add a required `account_number` field (`"581853207"`) to every `place_equity_order` and `cancel_equity_order` call. Orders sent to an account without `agentic_allowed=true` will be rejected.
- Add a `ref_id` UUID parameter to every `place_equity_order` call (idempotency key; see Step 4 below).
- Add `time_in_force` (default `"gfd"` for day orders, `"gtc"` for stops) and `market_hours` (default `"regular_hours"`) parameters.
- Update `client.preview_order()` to call `review_equity_order` instead of the old `preview_order` tool. `review_equity_order` is the SAFE simulation: it returns pre-trade alerts, estimated fill, and does not move money.
- Update `client.get_account()` to call `get_accounts` (for account metadata including `agentic_allowed`, cash balance) and `get_portfolio` (for authoritative `buying_power`). Buying power from `get_portfolio` is the single source of truth for cash available.

**Agentic-account guard (new code):**  
In `src/mcp_client.py`, add a method `assert_agentic_account(account_number: str)` that calls `get_accounts`, filters for `account_number`, and raises `MCPError("agentic_not_allowed")` if the record's `agentic_allowed` field is not `True`. Call this in `Application._build_controller()` for the production controller before any live session starts.

---

## PRIORITY 2 — Session-Start Safety Verifications

These checks must run every time the production controller initializes in LIVE mode, before any order is submitted. They should live in a new function `src/operator/startup_checks.py` (or added to `src/operator/eligibility.py`) called from `Application._build_controller()` when `env_name == "production"` and mode is LIVE.

### Step 2A: Cash-account / margin-disabled verification
**What:** Call `get_accounts`, retrieve the record for account `581853207`, and assert:
- `account_type == "cash"` (not `"margin"`).
- `margin_enabled == False` (or the equivalent field — verify field names from the live `get_accounts` response).
- If either assertion fails: raise, log `CRITICAL_SESSION_HALT: margin detected`, halt the session, and alert the operator.

**Why:** INSIGHTS.md §4 — the Margin Account Agreement is already signed and creates a first-priority lien over all positions even for cash-account users. The "30-day cash-only" operating policy is not in the legal agreement; it exists only as an operational rule that the app must enforce. If Robinhood ever enables margin for this account (e.g., a Gold upsell, ACH reversal creating debit balance), the AI could unknowingly trade on margin with interest, hypothecation, and forced-liquidation exposure. The app must verify at every session start, never assume.

**App mapping:** Hooks into the `Application._build_controller()` flow for the production path; blocks live trading via `ControlPlane.arm_trading()` → `eligibility_check()`.

---

### Step 2B: Buying-power and deployment-cap verification
**What:** Call `get_portfolio` at session start to get the authoritative `buying_power`. Verify it is within expected range (alert if wildly different from last known balance). Then enforce the deployment cap (see Step 3 below).

**Why:** `get_portfolio` is the authoritative source; `get_accounts` may return a stale or summary figure. The deployment cap math must be based on ground truth, not a cached internal figure.

---

## PRIORITY 3 — Deployment Cap + Passcode Guardrail

### Step 3: Enforce the $500 deployment cap at the risk gate
**What:** Add a new check to `RiskGate.check()` in `src/risk.py`:

```python
# Deployment cap: total notional deployed (all open positions) must not
# exceed DEPLOYMENT_CAP_USD. Overridable only with the operator passcode.
DEPLOYMENT_CAP_USD = 500.0   # 50% of the $1,000 funded balance
if not acct.deployment_cap_override:
    if acct.gross_exposure + notional > DEPLOYMENT_CAP_USD + 1e-9:
        v.append("deployment_cap_exceeded")
```

The `AccountState` dataclass (`src/risk.py` lines 38–46) needs a new field: `deployment_cap_override: bool = False`.

**Passcode enforcement:** The operator slash-command interface (`src/operator/control.py` or a new `/cap-override` command) must prompt for a passcode when the operator requests a deployment-cap override. Compare the submitted passcode against the expected value (`"pinappleexpress9"`) using a constant-time comparison (`hmac.compare_digest`). A correct passcode sets `deployment_cap_override = True` in the current `AccountState` for the remainder of the session only — it does NOT persist across restarts. Log the override event to the immutable audit log (see Step 5) with a timestamp and a record that the operator authorized it.

**Why:** The operator's stated goal is "make money without losing capital; do not deploy all capital at once." A $500 cap limits maximum drawdown to 50% of the account even in a complete wipeout of all deployed positions. The passcode requirement prevents the AI from auto-escalating the cap based on a misread instruction — only a human who knows the passcode can override.

**App mapping:** `src/risk.py` `RiskGate.check()` is the correct enforcement point because no LLM agent can override it (per the architecture's "rule layer is bedrock" principle stated in README.md). The `AccountState` object is built in `src/controller.py` before calling `RiskGate.check()`; `gross_exposure` is already tracked there.

---

## PRIORITY 4 — Immutable Audit Logging

### Step 4: Log every AI-proposed and AI-executed action
**What:** Create `src/audit.py` implementing an append-only audit log (SQLite WAL in `data/prod/audit.db`, separate from the trading `trader.db`). Every entry must include:

| Field | Value |
|---|---|
| `ts_utc` | UTC ISO-8601 timestamp |
| `ts_et` | US/Eastern timestamp |
| `entry_id` | UUID (never reused) |
| `event_type` | `PROPOSED` / `REVIEWED` / `PLACED` / `CANCELLED` / `FILL` / `STOP_PLACED` / `CAP_OVERRIDE` / `KILL` / `SESSION_START` / `SESSION_END` |
| `account_number` | `"581853207"` |
| `symbol` | ticker or `""` |
| `side` | `buy` / `sell` / `""` |
| `order_type` | `limit` / `stop_market` / `stop_limit` / `""` |
| `quantity` | shares or `0` |
| `price` | limit/stop price or `0` |
| `ref_id` | UUID idempotency key sent to Robinhood |
| `review_result` | output of `review_equity_order` as JSON string |
| `thesis_id` | FK to insight/thesis record |
| `conviction_score` | float |
| `approved_by` | `"autonomous"` / `"operator"` |
| `outcome` | Robinhood's response as JSON string |
| `risk_verdict` | serialized `RiskVerdict` |
| `violations` | serialized list of violations (if any) |

The table must be `CREATE TABLE IF NOT EXISTS` with `WITHOUT ROWID` and WAL mode. Insertions must use `INSERT OR IGNORE` keyed on `entry_id` to be idempotent. **No UPDATE or DELETE operations are ever performed on this table** — immutability is enforced by not providing those methods in the API.

**Why:** INSIGHTS.md §8 Priority 1a — Section 29.8 places 100% liability on the operator for every trade including hallucinations and malfunctions. "Robinhood will not be liable." In a FINRA arbitration (§39), the operator needs a contemporaneous, non-repudiable record of what the AI actually proposed, what `review_equity_order` said, whether a human approved it, and what the broker returned. Six-year retention is FINRA Rule 4511 best practice. The audit log must be stored off the trading path (separate file) so a corrupted `trader.db` does not destroy the audit trail.

**Idempotency (ref_id):** Each call to `place_equity_order` must include a `ref_id` (UUID4, generated once per `OrderRequest` in `ExecutionHandler.submit()`, stored in the audit log before placing the order). If the network request times out and retries, the same `ref_id` means Robinhood will not double-fill. This closes a real race condition in the current `execution.py`: a timeout after submit but before the response is received currently has no protection against a duplicate order.

**App mapping:** `ExecutionHandler.submit()` in `src/execution.py` is the right place to fire `PROPOSED`, `REVIEWED`, `PLACED`, and `FILL` events. `RiskGate.check()` fires the `risk_verdict` record. The killswitch evaluator fires `KILL` events. `ControlPlane.trading(on=True)` fires `SESSION_START`.

---

## PRIORITY 5 — Review-Before-Place: Mandatory Pre-Trade Preview

### Step 5: Enforce review_equity_order before every place_equity_order
**What:** In `ExecutionHandler.submit()` (`src/execution.py` lines 78–81), replace the current direct `client.place_order()` call with a two-step sequence:

1. Call `client.preview_order()` (which maps to `review_equity_order`). Parse the response for pre-trade alerts (margin warning, tradability flags, estimated cost). Log the result to the audit log as `event_type=REVIEWED`.
2. If the preview returns any blocking alert (e.g., `tradability_blocked`, `insufficient_buying_power`, `margin_required`), reject the order immediately without placing it. Log as `event_type=PROPOSED` with `outcome=preview_blocked`.
3. If the preview is clean, proceed to `client.place_order()` (which maps to `place_equity_order`). Log as `event_type=PLACED`.

**Human-in-the-loop flow (autonomous vs operator-approved):**  
The existing `ControlPlane` (`src/operator/control.py`) already models `trading_armed` as a per-session human gate. At the individual-trade level, add a configurable approval window:
- **Autonomous mode (default for small trades):** If `notional <= AUTONOMOUS_THRESHOLD_USD` (suggest $50 initially) and the risk gate approves, execute without waiting for operator input. Log `approved_by="autonomous"`.
- **Human-approval mode (for larger trades or during initial live period):** If `notional > AUTONOMOUS_THRESHOLD_USD`, enqueue the proposed order in a `PendingQueue`, send an operator notification (via the existing `src/monitoring/notifications.py`), and wait up to `APPROVAL_TIMEOUT_S` (suggest 60 seconds). If the operator approves via slash command (`/approve <ref_id>`), proceed. If the operator rejects or the window expires, cancel the proposal. Log `approved_by="operator"` or `approved_by="timed_out_cancelled"`.

**Passcode and the autonomous bypass:** The `/approve` command and the autonomous-mode configuration must be accessible only from the operator's terminal session. If the AI instructs itself to auto-approve via a prompt chain, that attempt must be logged and rejected (the approval path must be reachable only from the operator's `ControlPlane` interface, not from inside the `Controller`'s decision loop).

**Why:** INSIGHTS.md §8 Priority 1b — Section 29.8 warns explicitly that "your AI agent may override your ability to review any actions proposed by your AI agent to the extent that you prompt or instruct your AI agent to do so." A mandatory preview step that runs even in autonomous mode, with its output logged, preserves evidence that the app ran the broker's own pre-trade checks and did not bypass them. The human-approval window for larger trades gives the operator the ability to exercise the review right that Section 29.8 recommends.

---

## PRIORITY 6 — Market Hours / Session Awareness

### Step 6: Wire market_hours parameter and session-appropriate strategies
**What:** The real `place_equity_order` tool accepts a `market_hours` parameter:
- `"regular_hours"` — NYSE/NASDAQ regular session (9:30 AM – 4:00 PM ET).
- `"extended_hours"` — pre-market and after-hours.
- `"all_day_hours"` — 24/5 (Sunday 8 PM – Friday 8 PM ET).

**Rules to enforce:**
1. **Default to `"regular_hours"`** for all strategies unless the strategy explicitly opts in to extended hours.
2. **During extended hours**, only limit orders are valid. Market orders must be blocked. The existing `place_order()` code already uses marketable limit orders, which is correct — but the `market_hours` field must be set explicitly, not left to the broker default.
3. **`get_equity_historicals`** supports `bounds` parameter values: `regular`, `extended`, `trading`, `24_5`, `24_7`, `hyper_trading`. For strategy backtesting, use `regular` to match the session in which the strategy will trade. For overnight / 24-5 strategies, use `trading` or `24_5`.
4. **No strategy currently in the registry is designed for extended or 24-5 trading.** Until a strategy is specifically backtested and validated in extended-hours data (using `bounds="extended"` in `get_equity_historicals`), set `market_hours="regular_hours"` globally and add a check to `ExecutionHandler.submit()` that rejects any order with `market_hours != "regular_hours"` unless that strategy's registry entry explicitly declares `extended_hours_approved=True`.

**Why:** Extended-hours markets have wider spreads, lower liquidity, and higher volatility. The risk parameters in `src/risk.py` (spread cap, position size) were calibrated for regular-hours trading. Operating strategies in extended hours without recalibration violates the falsify-before-adopt principle. Also, extended-hours order types are more restricted — a market order in extended hours is silently queued to open at regular hours, which is unexpected behavior for an autonomous system.

**App mapping:** `market_hours` parameter added to `place_equity_order` call in `src/mcp_client.py`. Strategy registry (`src/strategies/registry.py`) gets a new optional field `extended_hours_approved: bool = False`. `ExecutionHandler.submit()` reads the strategy name from `OrderRequest` and checks the registry flag.

---

## PRIORITY 7 — Broker Outage Detection and Safe State

### Step 7: Wire killswitch #4 and #23 to the real MCP heartbeat
**What:** Killswitch #4 (`mcp_failure`) in `src/killswitch.py` (line 89) fires when `mcp_heartbeat_age_s > 60`. The `KillswitchState` field is defined (line 47) but the actual heartbeat signal is not yet wired (noted in `data/build_status.md` under "REMAINING POLISH"). To wire it:

1. Add an async heartbeat task in `src/app.py` or `src/controller.py` that calls `get_accounts` (a lightweight read) every 30 seconds during market hours and updates `KillswitchState.mcp_heartbeat_age_s`.
2. On three consecutive failures (90 seconds), fire the `HALT_SESSION` scope from killswitch #4.
3. On entering the halt: (a) attempt to cancel all open orders via `cancel_equity_order` for each order ID retrieved from `get_equity_orders`; (b) log `event_type=KILL` with reason `"broker_outage"` to the audit log; (c) send operator notification: "HOOD DaBang halted — cannot reach Robinhood API. Open the Robinhood app immediately to manage open positions. Phone: 650-772-5277."
4. Do NOT retry new orders during the outage. Enter read-only mode. Do NOT automatically flatten positions via API during an outage — the cancellation requests themselves may not be reaching the broker.
5. Resume only when heartbeat recovers AND the operator explicitly runs `/arm` again.

**Why:** Customer Agreement §29.7(g) — "API/MCP connectivity is not guaranteed" during disruptions. BCP (INSIGHTS.md §5) provides no recovery time objective. §14.3 disclaims liability for losses from system interruptions. If the broker goes dark mid-position with an unprotected stop order that hasn't confirmed, the app must tell the operator immediately, not retry silently.

**App mapping:** Killswitch #23 ("broker_outage") is listed in `build_status.md` as an interface-only killswitch needing wiring. This step wires it.

---

## PRIORITY 8 — Immutable Audit: Trade Confirmation Monitoring

### Step 8: Reconcile broker confirmations within the 2-day window
**What:** After each order fill, call `get_equity_orders` to retrieve the broker's own record of the order and cross-reference it against the audit log entry. Specifically check:
- Symbol matches.
- Side (buy/sell) matches.
- Quantity is at or below the ordered quantity (partial fills are valid; excess fills are a red flag).
- The broker order ID matches what `place_equity_order` returned.

If any mismatch is found: log `CRITICAL_DESYNC`, fire killswitch #5 (`reconciliation_desync` in `src/killswitch.py` line 94), and alert the operator immediately.

**Why:** Customer Agreement §4.6 — confirmations are binding unless objected to within 2 business days. An autonomous system trading without per-trade human attention must self-monitor for unrecognized trades. Also, INSIGHTS.md §8 Priority 1b — if an AI hallucination causes a wrong ticker or wrong size to reach the broker, the reconciliation step is the first line of detection. The existing `src/execution.py` has a reconciliation placeholder; this step fully wires it to the real `get_equity_orders` tool.

---

## PRIORITY 9 — Data Minimization (NPI Leaving Robinhood's Perimeter)

### Step 9: Minimize what account data is sent to LLM providers
**What:** Review every `InsightEngine` call, `LLMClient` prompt, and agent invocation in `src/insight/`, `src/agents/`, and `src/llm/` to audit what account data appears in the prompt context. Apply these rules:

1. **Never send full account balance or position history in raw form.** Instead send derived summaries: "current position: 100 shares AAPL at $185.20 average" — not "account statement: $1,000 cash, $18,520 AAPL position, $481 MSFT position."
2. **Never send the account number (581853207) in any prompt.**
3. **Never send PII** (name, email, SSN, address) in prompts. These fields should never appear in any MCP read result that gets forwarded to the AI — strip them before including in context.
4. **Log what is sent:** For each LLM call, record in the LLM ledger (`data/prod/llm_ledger.db`) the category of account data included in the prompt (not the raw data, just a classification tag like `"position_summary"`, `"quote_data"`, `"no_account_data"`).
5. **For the insight/thesis engine,** the strategy signal and market data are appropriate to include. The account's buying power can be expressed as a single number ("available capital: $500") without the full account snapshot.

**Why:** Financial Privacy Notice "Agentic Trading" provision (INSIGHTS.md §3) — every piece of NPI sent to Claude (or any AI provider) "is not subject to Robinhood's privacy commitments" and "revocation does not require the AI provider to delete previously shared data." Minimizing what is sent limits the irrevocable privacy exposure. The LLM provider (Anthropic) also has its own data-use terms, and some model tiers use conversation data for training by default. Sending the minimum necessary is both a privacy protection and a prompt-injection defense.

---

## PRIORITY 10 — The Paper-Prove-Then-Promote Path

### Step 10: Run strategies through all five gates before any live promotion
**What:** The strategy registry (`src/strategies/registry.py`) enforces `FIVE_GATES` and blocks promotion to `live` unless all five pass. The eligibility check in `src/operator/eligibility.py` enforces `>=1 strategy has passed all five gates` AND `>=30 paper trades` AND `positive paper expectancy`. These gates are ALREADY built and cannot be bypassed. The operator's task is to run each candidate strategy through the validation pipeline:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_strategy.py --ticker SPY --strategy <name>
```

**Five gates (already built):**
1. **Walk-forward:** Out-of-sample Sharpe > 0 on rolling windows.
2. **Bootstrap Probability of Backtest Overfitting (PBO):** Deflated Sharpe Ratio > 0.
3. **Deflated Sharpe Ratio (DSR):** Accounts for multiple testing; DSR > 0.
4. **Out-of-sample (OOS):** Hold-out period independent of optimization.
5. **Live-lock:** Registry gate — all four above must pass or the strategy stays in `paper`.

**Paper period requirements before live:**
- Minimum 30 paper trades on the current strategy mix.
- Paper expectancy > 0R (positive average R-multiple per trade).
- All self-tests green (`make test`).
- Operator must pass `dod_overrides=True` to acknowledge the 12-point Definition of Done (§35).

**Expected outcome:** Most strategies will fail these gates. That is the intended behavior. The system is designed to refuse live trading on no-edge strategies. Only gate-passers are candidates for the first live trade.

**Why:** The falsify-before-adopt philosophy (hood-dabang-risk-philosophy.md). Every paper dollar of loss in the validation period is information; every real dollar of loss before validation is waste. The five gates are the only empirical basis for a probabilistic claim that an edge exists. Without them, the first live trades are pure speculation with the operator bearing 100% liability under §29.8.

---

## PRIORITY 11 — The First Live Trade Checklist

When at least one strategy clears all five gates and the paper period requirements are met, the first live trade must follow this sequence without exception:

### Pre-trade
- [ ] Run `make test` — all 406+ tests green.
- [ ] Run `client.discover()` and `client.validate_tool_map()` — zero mismatched tools.
- [ ] Call `get_accounts` — confirm `account_number=581853207`, `agentic_allowed=True`, `account_type="cash"`, `margin_enabled=False`.
- [ ] Call `get_portfolio` — confirm `buying_power >= 0` and consistent with expected balance. Record the value.
- [ ] Confirm `buying_power <= $500` available for deployment (deployment cap). If not, the cap is the binding constraint.
- [ ] Confirm no open positions in `get_equity_positions` (start clean).
- [ ] Confirm no open orders in `get_equity_orders` (start clean).
- [ ] Confirm all killswitches clear: `killswitch.evaluate(state)` returns empty list.
- [ ] Start the audit log: write `SESSION_START` entry with account snapshot.

### At the proposed trade
- [ ] The strategy has passed all five validation gates.
- [ ] The ConvictionGate has scored the setup (both Stage 1 and Stage 2 pass). `conviction_score >= execution_floor`.
- [ ] A falsifiable thesis exists (`thesis_id` is set, `has_thesis=True`).
- [ ] `RiskGate.check()` approves: `approved=True`, `violations=[]`. Verify:
  - `notional <= $500` deployment cap (or operator has entered passcode override).
  - `risk_dollars <= per_trade_risk_pct × effective_capital`.
  - `spread_pct` below cap.
  - `gross_exposure + notional <= total_exposure_cap_pct × equity`.
- [ ] Call `review_equity_order` (preview). Read the full response. Confirm:
  - No margin requirement.
  - Tradability: `is_tradable=True`.
  - Estimated cost within expected range.
  - No pre-trade alerts blocking the order.
  - Log the preview response to the audit log (`event_type=REVIEWED`).
- [ ] **Stop is specified:** `stop_price < entry_price` for longs (stop will be placed via `place_equity_order` with `type="stop_market"`). Confirm the stop represents an acceptable loss in R (≤1R per the risk parameters).
- [ ] **Size is small:** For the first live trade, use the minimum viable size. The point is to prove the live flow works, not to maximize profit. Suggest `shares=1` for a stock priced under $50 (max $50 notional for the first trade).
- [ ] Operator reviews the proposed trade and approves via `/approve <ref_id>` (human-in-the-loop mode enforced for the first 10 live trades regardless of the autonomous threshold).

### At execution
- [ ] Log `event_type=PROPOSED` with full trade details before calling the broker.
- [ ] Call `place_equity_order` with:
  - `account_number="581853207"`
  - `symbol`, `side`, `type="limit"`, `quantity`, `limit_price`
  - `time_in_force="gfd"` (good for day)
  - `market_hours="regular_hours"`
  - `ref_id=<UUID>` (the same UUID logged in the audit entry)
- [ ] Log `event_type=PLACED` with the broker's order ID.
- [ ] Within 2 seconds of fill confirmation, place the stop:
  - Call `place_equity_order` with `type="stop_market"`, exit side (sell for long), `quantity=filled_shares`, `stop_price`, `time_in_force="gtc"`, `ref_id=<entry_ref_id>+"-stop"`.
  - If stop placement fails or times out: FLATTEN immediately (place a market-limit sell for the filled quantity). Log `event_type=KILL` with reason `"unhedged_position"`. This is killswitch #27.
- [ ] Log `event_type=STOP_PLACED` with the stop order ID.
- [ ] Reconcile: call `get_equity_orders` within 60 seconds. Confirm the broker's record matches the audit log.

### Post-trade monitoring
- [ ] Monitor the heartbeat (killswitch #4) continuously.
- [ ] On stop trigger: log fill event, close the position in `trader.db`, compute realized PnL, write thesis outcome.
- [ ] Write `SESSION_END` to audit log.

---

## PRIORITY 12 — Market Manipulation Pattern Monitoring

### Step 12: Self-monitor trading patterns for regulatory risk
**What:** After each week of live trading, run a pattern scan over the audit log entries:

- **Cancellation rate:** If more than 30% of proposed orders are cancelled before partial fill, this resembles spoofing. Alert the operator.
- **Wash-sale proximity:** If the audit log shows a sell followed by a buy in the same symbol within 30 days at a loss, flag as a potential wash-sale tax event (not necessarily illegal, but requires cost-basis adjustment).
- **Order rate:** Killswitch #17 (`order_rate_amplification`) in `src/killswitch.py` (line 115) already covers runaway order rate. Verify it is wired.
- **Closing auction proximity:** Flag any order placed within 5 minutes of 4:00 PM ET that represents more than 1% of the day's volume in that ticker (marking-the-close risk).

**Why:** INSIGHTS.md §8 Priority 2b; Customer Agreement §29.8 paragraph 4 — "you assume full responsibility for the same regardless of whether such conduct was intended by you." Criminal market manipulation exposure exists even for unintentional patterns generated by an autonomous AI.

---

## PRIORITY 13 — Ongoing Operations

### Step 13A: Monitor trade confirmations within 2 business days
**What:** After each session, pull `get_equity_orders` for the day and compare every broker record against the audit log. Any order in the broker's records that does not match an audit log entry is an anomaly requiring immediate operator review. Implement this as a scheduled post-session reconciliation step.

**Why:** Customer Agreement §4.6 — confirmations are binding unless objected to within 2 business days. The only way to catch unauthorized or erroneous trades in time to object is automated reconciliation.

### Step 13B: Version-track Robinhood's legal documents
**What:** Quarterly (set a calendar reminder), re-download all 7 documents from Robinhood and diff them against the copies in `/Users/alarkpatel/CLAUDE_MASTER/robinhood-legal/`. If Section 29.8 changes — especially if new restrictions on AI agents are added or liability language shifts — review the change before the next live session.

**Why:** Customer Agreement §37.7 — Robinhood may amend "at any time without prior notice." Continued account use constitutes acceptance.

### Step 13C: Wash-sale and tax record-keeping
**What:** Maintain a running cost-basis register in the audit log, tracking every buy/sell pair, holding period, and wash-sale flags. Export quarterly for tax preparation.

**Why:** Customer Agreement §18.1 places tax reporting responsibility on the operator. Robinhood's 1099 does not cover all wash-sale scenarios (especially cross-account wash sales or fractional share rounding).

---

## RISKS / OPEN QUESTIONS

1. **`agentic_allowed` field name is unconfirmed.** The `get_accounts` response fields (`agentic_allowed`, `account_type`, `margin_enabled`) are inferred from the context provided. The exact JSON field names must be verified by inspecting the live `get_accounts` response before wiring the session-start checks in Step 2A. A field-name mismatch could allow the session to proceed without a valid check.

2. **`review_equity_order` may not simulate stop orders.** The preview tool may only support `type="limit"` and `type="market"`. If `type="stop_market"` is not supported by `review_equity_order`, the stop-attachment step cannot be previewed, only placed live. This would mean the stop is the one order type that cannot be pre-validated. Verify by calling `review_equity_order` with `type="stop_market"` in a sandbox context before assuming it works.

3. **Partial fills on stop_market orders.** `place_equity_order` with `type="stop_market"` will execute at the market price once the stop level is touched. In a fast market, the fill may be significantly worse than the stop price. The existing `ExecutionHandler._flatten()` path handles unconfirmed stop placements, but does not handle a confirmed-but-badly-filled stop. Consider adding a stop-slippage alert if `avg_fill_price < stop_price * 0.98` for a long.

4. **24-5 / extended-hours session risk.** If a GTC stop order is live overnight and Robinhood's 24-5 session triggers it at 2 AM ET, the fill price in an illiquid market may be far from the stop. The current strategy set was not designed or validated for overnight holding. Verify that all `time_in_force="gtc"` stop orders are marked `market_hours="regular_hours"` so they do not trigger in extended sessions unless the strategy explicitly opts in.

5. **No API uptime SLA from Robinhood.** The BCP provides no contractual SLA for API availability. If the Robinhood API is down during a volatile market move with an open position, HOOD DaBang cannot cancel orders or place new stops. The operator must have the Robinhood mobile app open and be prepared to manage positions manually. Phone: 650-772-5277.

6. **`get_equity_tradability` is not yet wired.** The real MCP surface includes `get_equity_tradability` which returns whether a symbol can be traded at a given time (regulatory holds, trading halts, etc.). The current `mcp_client.py` has no wrapper for this. A halted security where HOOD DaBang attempts to place an order will be rejected by the broker — which is recoverable — but adds an unnecessary rejection to the audit log and increments the consecutive-rejection counter toward killswitch #12.

7. **Deployment cap math uses notional, not risk dollars.** The $500 cap is applied to gross notional exposure (`gross_exposure + notional`). An alternative is to cap total risk dollars. At the current risk parameters (per-trade risk ≤ 2.5% of effective capital ≈ $12.50 per trade), the risk-dollars approach would allow more concurrent positions within the same risk budget. This is a deliberate design choice to be reviewed after the first 30 live trades.

8. **Passcode storage.** The passcode `"pinappleexpress9"` must never appear in committed source code, logs, or the audit database in plaintext. Store it as an environment variable (`HOOD_CAP_OVERRIDE_PASSCODE`) and compare with `hmac.compare_digest`. The current runbook references it in plaintext for bootstrapping only — rotate it once the env var is set.

---

*Prepared by: Claude Code (claude-sonnet-4-6) · 2026-06-15 · For operator use only. This document is operational planning, not legal advice.*
