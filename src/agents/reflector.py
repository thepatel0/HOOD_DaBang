"""
HOOD DaBang — Reflector (Brief §5.2, §7.4, §26.12).

Per closed trade: a short reflection + a thesis-vs-reality score (did the stated
mechanism drive the move; did invalidation fire correctly; was the base rate
accurate). Categorizes each loss GOOD (correct setup, market disagreed) vs BAD
(rule violation / forced / chased / ignored invalidation). Per session: flags
overtrading (>10 trades). Deterministic core ($0); the scores feed memory and the
theses table so the Meta-Learner learns which MECHANISMS actually predict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TradeReflection:
    trade_id: int
    ticker: str
    pnl_r: float
    good_or_bad_loss: str            # "good" | "bad" | "n/a"
    mechanism_was_correct: Optional[bool]
    invalidation_fired_correctly: Optional[bool]
    base_rate_was_accurate: Optional[bool]
    text: str


@dataclass
class SessionReflection:
    n_trades: int
    wins: int
    expectancy_r: float
    overtrading_flag: bool
    bad_losses: int
    notes: str


# exit reasons that indicate the system behaved correctly on a loss
_CLEAN_LOSS_EXITS = {"stop", "lost_vwap", "reclaimed_vwap", "time_stop",
                     "killswitch", "invalidation"}
# exit reasons that suggest a process failure on a loss
_BAD_LOSS_EXITS = {"manual", "chased", "forced", "revenge"}


class Reflector:
    def __init__(self, llm_client=None):
        self.llm = llm_client

    def reflect_trade(self, *, trade_id: int, ticker: str, side: str, pnl_r: float,
                      exit_reason: str, base_rate: Optional[float],
                      invalidation_should_have_fired: bool = False) -> TradeReflection:
        win = pnl_r > 0

        # thesis-vs-reality (deterministic inference)
        mechanism_ok = win  # mechanism "drove the move" if the trade worked
        # invalidation fired correctly if a loss exited via a clean stop/invalidation,
        # OR a win never needed it
        if win:
            invalidation_ok = not invalidation_should_have_fired
        else:
            invalidation_ok = any(k in exit_reason for k in _CLEAN_LOSS_EXITS)
        # base rate accurate if outcome roughly matches a >50% base rate expectation
        base_rate_ok = None
        if base_rate is not None:
            base_rate_ok = (win == (base_rate >= 0.5))

        # good vs bad loss
        if win:
            gbl = "n/a"
        elif any(k in exit_reason for k in _BAD_LOSS_EXITS) or invalidation_should_have_fired:
            gbl = "bad"
        elif any(k in exit_reason for k in _CLEAN_LOSS_EXITS):
            gbl = "good"
        else:
            gbl = "bad"

        text = self._text(ticker, side, pnl_r, exit_reason, gbl, win)
        return TradeReflection(trade_id, ticker, round(pnl_r, 3), gbl, mechanism_ok,
                               invalidation_ok, base_rate_ok, text)

    def _text(self, ticker, side, pnl_r, exit_reason, gbl, win) -> str:
        if self.llm is not None:
            r = self.llm.call("reflection", "reflector",
                              "You are the Reflector. In 3 sentences: the setup, what "
                              "happened, and what to do differently. Be concrete.",
                              [{"role": "user", "content":
                                f"{ticker} {side} closed {pnl_r:+.2f}R via {exit_reason}"}],
                              max_tokens=200)
            if r.spent and r.text:
                return r.text
        outcome = "won" if win else f"lost ({gbl} loss)"
        return (f"{ticker} {side} {outcome} at {pnl_r:+.2f}R via {exit_reason}. "
                f"{'Mechanism played out.' if win else 'Setup was '+( 'sound; market disagreed.' if gbl=='good' else 'compromised by process.')} "
                f"{'Repeat the process.' if (win or gbl=='good') else 'Investigate the rule break.'}")

    def reflect_session(self, trades: List[dict], ceiling: int = 10) -> SessionReflection:
        n = len(trades)
        wins = sum(1 for t in trades if t.get("pnl_r", 0) > 0)
        exp = (sum(t.get("pnl_r", 0) for t in trades) / n) if n else 0.0
        bad = sum(1 for t in trades if t.get("good_or_bad_loss") == "bad")
        overtrading = n > ceiling
        notes = (f"{n} trades, {wins} wins, expectancy {exp:+.2f}R, {bad} bad losses."
                 + (" OVERTRADING FLAG — investigate." if overtrading else ""))
        return SessionReflection(n, wins, round(exp, 3), overtrading, bad, notes)
