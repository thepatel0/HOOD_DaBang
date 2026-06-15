"""
HOOD DaBang — LLM budget tracker (Brief §3, §26.7).

Every LLM call logs its tokens + dollar cost to data/llm_ledger.db. The budget
tracker aggregates spend and exposes the daily/monthly state the Token Decision
Engine reads to fail-closed (pause LLM agents while Tier 0 keeps trading).

Cost model mirrors Brief §3.2/§3.6: cached input billed at ~10%.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from .token_decision_engine import BudgetState


class LLMBudget:
    def __init__(self, ledger_conn: sqlite3.Connection, cfg: dict,
                 now: Callable[[], datetime] = None):
        self.conn = ledger_conn
        self.daily_budget = cfg["llm"]["daily_budget_usd"]
        self.monthly_budget = cfg["llm"]["monthly_budget_usd"]
        self.pricing = cfg["llm"]["pricing"]
        self.now = now or (lambda: datetime.now(timezone.utc))

    # ----- cost model ---------------------------------------------------- #
    def cost(self, model: str, in_tokens: int, out_tokens: int,
             cached_tokens: int = 0) -> float:
        if model not in self.pricing:
            return 0.0
        p = self.pricing[model]
        fresh_in = max(0, in_tokens - cached_tokens)
        return (fresh_in * p["input"] + cached_tokens * p["input"] * 0.10
                + out_tokens * p["output"]) / 1_000_000.0

    # ----- record a call ------------------------------------------------- #
    def record(self, agent: str, model: str, in_tokens: int, out_tokens: int,
               cached_tokens: int = 0, latency_ms: int = 0) -> float:
        c = self.cost(model, in_tokens, out_tokens, cached_tokens)
        self.conn.execute(
            "INSERT INTO llm_calls (ts, agent, model, input_tokens, cached_tokens, "
            "output_tokens, cost_usd, latency_ms) VALUES (?,?,?,?,?,?,?,?)",
            (self.now().isoformat(), agent, model, in_tokens, cached_tokens,
             out_tokens, c, latency_ms))
        self.conn.commit()
        return c

    # ----- aggregates ---------------------------------------------------- #
    def spent_today(self) -> float:
        day = self.now().date().isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls WHERE substr(ts,1,10)=?",
            (day,)).fetchone()
        return float(row[0])

    def spent_month(self) -> float:
        month = self.now().strftime("%Y-%m")
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls WHERE substr(ts,1,7)=?",
            (month,)).fetchone()
        return float(row[0])

    def cache_hit_rate(self) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cached_tokens),0), COALESCE(SUM(input_tokens),0) "
            "FROM llm_calls WHERE substr(ts,1,10)=?",
            (self.now().date().isoformat(),)).fetchone()
        cached, total = float(row[0]), float(row[1])
        return (cached / total) if total > 0 else 0.0

    def state(self, budget_pause_flag: bool = False) -> BudgetState:
        return BudgetState(
            daily_spent_usd=self.spent_today(), daily_budget_usd=self.daily_budget,
            monthly_spent_usd=self.spent_month(), monthly_budget_usd=self.monthly_budget,
            budget_pause_flag=budget_pause_flag)
