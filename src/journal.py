"""
HOOD DaBang — journal / persistence (Brief §33, §26.12).

The single source of truth for what the system did and why. Writes theses,
conviction decisions, trades, the live positions mirror, and the equity curve to
data/trader.db. Every live trade MUST reference a stored thesis (FK), enforcing
the no-thesis-less-trade rule at the data layer.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional

from .insight.thesis import Thesis


class Journal:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ----- theses -------------------------------------------------------- #
    def record_thesis(self, thesis: Thesis, created_ts: str) -> str:
        tid = thesis.id()
        self.conn.execute(
            "INSERT OR REPLACE INTO theses (id, ticker, direction, claim, mechanism, "
            "drivers, invalidation, expected_path, confidence, base_rate, "
            "time_horizon_minutes, created_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, thesis.ticker, thesis.direction, thesis.claim, thesis.mechanism,
             json.dumps([d.__dict__ for d in thesis.drivers]),
             json.dumps(thesis.invalidation), thesis.expected_path,
             thesis.confidence, thesis.base_rate, thesis.time_horizon_minutes,
             created_ts))
        self.conn.commit()
        return tid

    def get_thesis(self, thesis_id: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM theses WHERE id=?",
                                (thesis_id,)).fetchone()
        if not row:
            return None
        cols = [c[0] for c in self.conn.execute("SELECT * FROM theses LIMIT 0").description]
        return dict(zip(cols, row))

    # ----- conviction log ----------------------------------------------- #
    def log_conviction(self, ts: str, ticker: str, strategy: str,
                       deterministic_score: float, final_score: Optional[float],
                       advanced: bool, traded: bool, reason: str) -> None:
        self.conn.execute(
            "INSERT INTO conviction_log (ts, ticker, strategy, deterministic_score, "
            "final_score, advanced, traded, reason) VALUES (?,?,?,?,?,?,?,?)",
            (ts, ticker, strategy, deterministic_score, final_score,
             int(advanced), int(traded), reason))
        self.conn.commit()

    # ----- positions mirror --------------------------------------------- #
    def open_position(self, ticker: str, shares: int, avg_price: float,
                      stop_order_id: str, strategy: str, thesis_id: str,
                      ts: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO positions (ticker, shares, avg_price, "
            "stop_order_id, strategy, thesis_id, opened_ts, last_reconciled_ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ticker, shares, avg_price, stop_order_id, strategy, thesis_id, ts, ts))
        self.conn.commit()

    def close_position(self, ticker: str) -> None:
        self.conn.execute("DELETE FROM positions WHERE ticker=?", (ticker,))
        self.conn.commit()

    def open_positions(self) -> Dict[str, int]:
        rows = self.conn.execute("SELECT ticker, shares FROM positions").fetchall()
        return {t: s for t, s in rows}

    # ----- trades -------------------------------------------------------- #
    def record_trade(self, *, ticker: str, strategy: str, strategy_version: str,
                     side: str, entry_ts: str, entry_price: float,
                     entry_shares: int, stop_price: float, conviction_score: float,
                     thesis_id: str, market_regime: str, order_id: str,
                     freshness_manifest: dict = None,
                     target_price: float = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO trades (ticker, strategy, strategy_version, side, entry_ts, "
            "entry_price, entry_shares, stop_price, target_price, conviction_score, "
            "thesis_id, market_regime, order_id, freshness_manifest) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticker, strategy, strategy_version, side, entry_ts, entry_price,
             entry_shares, stop_price, target_price, conviction_score, thesis_id,
             market_regime, order_id, json.dumps(freshness_manifest or {})))
        self.conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, *, exit_ts: str, exit_price: float,
                    exit_reason: str, pnl_dollars: float, pnl_r: float) -> None:
        self.conn.execute(
            "UPDATE trades SET exit_ts=?, exit_price=?, exit_reason=?, "
            "pnl_dollars=?, pnl_r=? WHERE id=?",
            (exit_ts, exit_price, exit_reason, pnl_dollars, pnl_r, trade_id))
        self.conn.commit()

    def closed_trades(self) -> List[dict]:
        rows = self.conn.execute(
            "SELECT id, ticker, strategy, pnl_r, pnl_dollars, exit_reason "
            "FROM trades WHERE exit_ts IS NOT NULL ORDER BY id").fetchall()
        return [dict(zip(["id", "ticker", "strategy", "pnl_r", "pnl_dollars",
                          "exit_reason"], r)) for r in rows]

    # ----- equity curve -------------------------------------------------- #
    def update_equity(self, ts: str, equity: float, daily_pnl: float,
                      drawdown_from_ath: float, ath: float,
                      effective_capital: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO equity_curve (ts, equity, daily_pnl, "
            "drawdown_from_ath, ath, effective_capital) VALUES (?,?,?,?,?,?)",
            (ts, equity, daily_pnl, drawdown_from_ath, ath, effective_capital))
        self.conn.commit()
