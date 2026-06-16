"""
HOOD DaBang — immutable audit log (NEXT_STEPS Priority 4; legal §29.8).

Append-only, off the trading path (its own SQLite file). Under §29.8 the operator
bears 100% liability for every AI trade including hallucinations; this log is the
contemporaneous, non-repudiable record of what the AI proposed, what
review_equity_order returned, whether a human approved, and what the broker did.

Immutability is enforced structurally: the API exposes ONLY append + read. There
is no update/delete method. Insert is idempotent on entry_id (INSERT OR IGNORE).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

EVENT_TYPES = {
    "SESSION_START", "SESSION_END", "PROPOSED", "REVIEWED", "PLACED", "FILL",
    "STOP_PLACED", "CANCELLED", "CAP_OVERRIDE", "KILL", "RECONCILE", "DESYNC",
    "APPROVED", "REJECTED",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
  entry_id TEXT PRIMARY KEY,
  ts_utc TEXT, ts_et TEXT, event_type TEXT, account_number TEXT,
  symbol TEXT, side TEXT, order_type TEXT, quantity REAL, price REAL,
  ref_id TEXT, thesis_id TEXT, conviction REAL, approved_by TEXT,
  review_result TEXT, outcome TEXT, risk_verdict TEXT, violations TEXT, note TEXT
) WITHOUT ROWID;
"""


@dataclass
class AuditLog:
    path: str = ":memory:"
    clock: Callable[[], datetime] = field(
        default=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # ----- append-only (NO update/delete is ever exposed) ---------------- #
    def record(self, event_type: str, *, account_number: str = "", symbol: str = "",
               side: str = "", order_type: str = "", quantity: float = 0.0,
               price: float = 0.0, ref_id: str = "", thesis_id: str = "",
               conviction: float = 0.0, approved_by: str = "autonomous",
               review_result: Any = None, outcome: Any = None,
               risk_verdict: Any = None, violations: Any = None,
               note: str = "") -> str:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown audit event_type {event_type!r}")
        now = self.clock()
        try:
            from zoneinfo import ZoneInfo
            ts_et = now.astimezone(ZoneInfo("America/New_York")).isoformat()
        except Exception:
            ts_et = now.isoformat()
        entry_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT OR IGNORE INTO audit (entry_id, ts_utc, ts_et, event_type, "
            "account_number, symbol, side, order_type, quantity, price, ref_id, "
            "thesis_id, conviction, approved_by, review_result, outcome, "
            "risk_verdict, violations, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (entry_id, now.isoformat(), ts_et, event_type, account_number, symbol,
             side, order_type, quantity, price, ref_id, thesis_id, conviction,
             approved_by, _j(review_result), _j(outcome), _j(risk_verdict),
             _j(violations), note))
        self.conn.commit()
        return entry_id

    def entries(self, event_type: Optional[str] = None, limit: int = 100) -> List[dict]:
        cols = [c[1] for c in self.conn.execute("PRAGMA table_info(audit)")]
        if event_type:
            rows = self.conn.execute(
                "SELECT * FROM audit WHERE event_type=? ORDER BY ts_utc DESC LIMIT ?",
                (event_type, limit)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit ORDER BY ts_utc DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]


def _j(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)
    except (TypeError, ValueError):
        return str(v)
