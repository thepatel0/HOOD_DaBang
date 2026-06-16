"""
HOOD DaBang — market-hours / session awareness (NEXT_STEPS Priority 6).

Maps the current US/Eastern time to a trading session and the Robinhood
`market_hours` order parameter. Robinhood supports:
  - regular_hours   : Mon-Fri 09:30-16:00 ET
  - extended_hours  : pre-market (04:00-09:30) and after-hours (16:00-20:00)
  - all_day_hours   : 24/5 overnight (Sun 20:00 ET -> Fri 20:00 ET, continuous)

Session rules the app enforces:
  - Default every order to regular_hours.
  - Extended/overnight allowed ONLY for orders explicitly flagged
    extended-hours-approved (no strategy is yet validated for thin sessions).
  - Extended/overnight: LIMIT orders only (never market) — wider spreads.
Deterministic, $0. `now` is injectable for testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, date
from typing import Callable, Optional, Set

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = None

# 2026 US market holidays (extend as needed; full-closure days)
HOLIDAYS_2026: Set[date] = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
}

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)
AFTERHOURS_CLOSE = time(20, 0)


@dataclass
class SessionInfo:
    session: str            # regular | pre_market | after_hours | overnight | closed
    market_hours: Optional[str]   # Robinhood param: regular_hours|extended_hours|all_day_hours|None
    limit_only: bool        # extended/overnight => limit orders only
    is_open: bool           # can we place an order at all?


def _now_et(now: Optional[datetime]) -> datetime:
    if now is not None:
        return now
    return datetime.now(ET) if ET else datetime.now()


def classify(now: Optional[datetime] = None,
             holidays: Optional[Set[date]] = None) -> SessionInfo:
    dt = _now_et(now)
    d, t, wd = dt.date(), dt.time(), dt.weekday()  # Mon=0 .. Sun=6
    holidays = holidays if holidays is not None else HOLIDAYS_2026

    weekday = wd < 5
    if weekday and d not in holidays:
        if REGULAR_OPEN <= t < REGULAR_CLOSE:
            return SessionInfo("regular", "regular_hours", False, True)
        if PREMARKET_OPEN <= t < REGULAR_OPEN:
            return SessionInfo("pre_market", "extended_hours", True, True)
        if REGULAR_CLOSE <= t < AFTERHOURS_CLOSE:
            return SessionInfo("after_hours", "extended_hours", True, True)

    # overnight 24/5: Sun 20:00 ET -> Fri 20:00 ET, excluding the regular/ext
    # windows already handled above. Closed: Fri 20:00 -> Sun 20:00, holidays.
    if _in_overnight(dt, holidays):
        return SessionInfo("overnight", "all_day_hours", True, True)
    return SessionInfo("closed", None, True, False)


def _in_overnight(dt: datetime, holidays: Set[date]) -> bool:
    wd, t = dt.weekday(), dt.time()
    # Friday after 20:00 and all Saturday and Sunday before 20:00 => fully closed
    if wd == 4 and t >= AFTERHOURS_CLOSE:
        return False
    if wd == 5:
        return False
    if wd == 6 and t < time(20, 0):
        return False
    # otherwise (weeknights between sessions, Sun >=20:00) treat as 24/5 overnight
    if dt.date() in holidays and time(9, 30) <= t < time(16, 0):
        return False
    return True


def market_hours_for(session_approved_extended: bool,
                     now: Optional[datetime] = None) -> Optional[str]:
    """The market_hours value to send. Regular session -> regular_hours always.
    Extended/overnight only if the order is approved for extended hours."""
    info = classify(now)
    if info.session == "regular":
        return "regular_hours"
    if not info.is_open:
        return None
    return info.market_hours if session_approved_extended else None
