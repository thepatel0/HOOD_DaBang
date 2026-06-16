"""
HOOD DaBang — database (Brief 33).

Canonical SQLite schema, WAL mode for power-loss safety. Pure stdlib.
`init_db(path)` is idempotent: safe to run daily as a reusable script.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL, strategy TEXT NOT NULL, strategy_version TEXT NOT NULL,
  side TEXT NOT NULL,
  entry_ts TEXT, entry_price REAL, entry_shares INTEGER,
  stop_price REAL, target_price REAL,
  exit_ts TEXT, exit_price REAL, exit_reason TEXT,
  pnl_dollars REAL, pnl_r REAL, fees REAL, slippage_dollars REAL,
  conviction_score REAL, thesis_id TEXT,
  setup_quality INTEGER, market_regime TEXT,
  good_or_bad_loss TEXT, lessons TEXT, freshness_manifest TEXT,
  order_id TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS theses (
  id TEXT PRIMARY KEY,
  ticker TEXT, direction TEXT, claim TEXT, mechanism TEXT,
  drivers TEXT, invalidation TEXT,
  expected_path TEXT, confidence REAL, base_rate REAL,
  time_horizon_minutes INTEGER, created_ts TEXT,
  mechanism_was_correct INTEGER, invalidation_fired_correctly INTEGER,
  base_rate_was_accurate INTEGER
);

CREATE TABLE IF NOT EXISTS conviction_log (
  id INTEGER PRIMARY KEY,
  ts TEXT, ticker TEXT, strategy TEXT,
  deterministic_score REAL, final_score REAL,
  advanced INTEGER, traded INTEGER, reason TEXT
);

CREATE TABLE IF NOT EXISTS strategy_stats (
  strategy TEXT, version TEXT, regime TEXT,
  n_trades INTEGER, win_rate REAL, avg_win_r REAL, avg_loss_r REAL,
  expectancy_r REAL, updated_ts TEXT, activation_status TEXT,
  gate_walkforward INTEGER, gate_bootstrap INTEGER, gate_dsr INTEGER,
  gate_oos INTEGER, gate_paper INTEGER,
  PRIMARY KEY (strategy, version, regime)
);

CREATE TABLE IF NOT EXISTS equity_curve (
  ts TEXT PRIMARY KEY, equity REAL, daily_pnl REAL,
  drawdown_from_ath REAL, ath REAL, effective_capital REAL
);

CREATE TABLE IF NOT EXISTS memory (
  id INTEGER PRIMARY KEY,
  layer TEXT, content TEXT, embedding BLOB, importance INTEGER,
  created_ts TEXT, last_confirmed_ts TEXT,
  confirmation_count INTEGER, contradiction_count INTEGER, status TEXT
);

CREATE TABLE IF NOT EXISTS positions (
  ticker TEXT PRIMARY KEY, shares INTEGER, avg_price REAL,
  stop_order_id TEXT, target_order_id TEXT,
  strategy TEXT, thesis_id TEXT, opened_ts TEXT, last_reconciled_ts TEXT
);

CREATE TABLE IF NOT EXISTS agent_calibration (
  agent TEXT PRIMARY KEY, brier_score REAL,
  predictions_logged INTEGER, updated_ts TEXT, weight REAL
);

CREATE TABLE IF NOT EXISTS build_status (
  component TEXT PRIMARY KEY,
  researched INTEGER, built INTEGER, tests_written INTEGER,
  tests_passing INTEGER, operator_approved INTEGER, notes TEXT, updated_ts TEXT
);

-- Research-mode output: decisions written here (and to memory) instead of orders.
CREATE TABLE IF NOT EXISTS recommendations (
  id INTEGER PRIMARY KEY,
  ts TEXT, ticker TEXT, side TEXT, strategy TEXT,
  entry REAL, stop REAL, target REAL, shares INTEGER,
  conviction REAL, thesis_id TEXT, regime TEXT,
  mechanism TEXT, invalidation TEXT, env TEXT,   -- env: production|paper
  followed INTEGER DEFAULT 0                       -- did a real trade follow it?
);
"""

LEDGER_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY,
  ts TEXT, agent TEXT, model TEXT,
  input_tokens INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
  cost_usd REAL, latency_ms INTEGER
);
"""


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def init_ledger(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(LEDGER_SCHEMA)
    conn.commit()
    return conn


def wal_enabled(conn: sqlite3.Connection) -> bool:
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    return str(mode).lower() == "wal"
