"""
HOOD DaBang — operator slash-command interface (Brief §22).

A dispatcher that maps `/command args` to a response string, reading live
controller state and the journal. Read-only commands (status, why, conviction,
rejected, budget, risk) are always available; mutating commands (halt, resume,
flatten, strategy on/off) change controller/registry state. Sensitive parameter
changes still require MANUAL_OVERRIDE.flag + 24h cooldown (enforced elsewhere).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


class CommandRouter:
    def __init__(self, controller=None, journal=None, budget=None, registry=None,
                 control=None):
        self.ctrl = controller
        self.journal = journal
        self.budget = budget
        self.registry = registry
        self.control = control          # ControlPlane (operating mode on/off)
        self._h: Dict[str, Callable[[List[str]], str]] = {
            "status": self._status, "halt": self._halt, "resume": self._resume,
            "flatten": self._flatten, "why": self._why, "thesis": self._thesis,
            "risk": self._risk, "conviction": self._conviction,
            "rejected": self._rejected, "why-no-trade": self._why_no_trade,
            "budget": self._budget, "strategy": self._strategy, "help": self._help,
            # operating-mode command & control
            "app": self._app, "research": self._research, "paper": self._paper,
            "trading": self._trading, "mode": self._mode,
            "recommendations": self._recommendations, "recommend": self._recommendations,
        }

    def _onoff(self, args: List[str]) -> Optional[bool]:
        if not args:
            return None
        return True if args[0].lower() in ("on", "start", "enable") else (
            False if args[0].lower() in ("off", "stop", "disable") else None)

    def dispatch(self, line: str) -> str:
        line = line.strip().lstrip("/")
        if not line:
            return self._help([])
        parts = line.split()
        cmd, args = parts[0], parts[1:]
        h = self._h.get(cmd)
        return h(args) if h else f"unknown command: /{cmd} (try /help)"

    # ----- read-only ----------------------------------------------------- #
    def _status(self, args) -> str:
        s = self.ctrl.state
        return (f"equity ${s.equity:,.2f} | day P&L ${s.day_pnl:+,.2f} "
                f"({s.day_pnl/s.session_start_equity:+.2%}) | trades {s.trades_today} "
                f"| floor {self.ctrl.gate.effective_execution_floor:.0f} "
                f"| {'HALTED: '+s.halt_reason if s.halted else 'ARMED'} "
                f"| {len(self.ctrl.open)} open")

    def _risk(self, args) -> str:
        s = self.ctrl.state
        dd = (s.ath - s.equity) / s.ath if s.ath else 0
        loss_room = s.day_pnl + 0.05 * s.session_start_equity
        return (f"per-trade cap {self.ctrl.cfg['adaptive_risk']['absolute_max_pct']:.1%} "
                f"(adaptive) | daily loss room ${loss_room:.2f} | DD {dd:.2%} "
                f"| consec losses {s.consecutive_losses}")

    def _conviction(self, args) -> str:
        rows = self.journal.conn.execute(
            "SELECT COUNT(*), SUM(advanced), SUM(traded) FROM conviction_log").fetchone()
        seen, adv, traded = rows[0], rows[1] or 0, rows[2] or 0
        hn = self.journal.conn.execute(
            "SELECT ticker, strategy, deterministic_score FROM conviction_log "
            "WHERE advanced=0 ORDER BY deterministic_score DESC LIMIT 1").fetchone()
        hnt = f"{hn[0]} {hn[1]} {hn[2]:.0f}" if hn else "none"
        return (f"signals seen {seen} | advanced {adv} | traded {traded} | "
                f"highest not taken: {hnt}")

    def _rejected(self, args) -> str:
        rows = self.journal.conn.execute(
            "SELECT ticker, strategy, deterministic_score, reason FROM conviction_log "
            "WHERE advanced=0 ORDER BY deterministic_score DESC LIMIT 10").fetchall()
        if not rows:
            return "no rejected signals logged"
        return "\n".join(f"  {t} {s} {sc:.0f} — {r}" for t, s, sc, r in rows)

    def _why_no_trade(self, args) -> str:
        if self.ctrl.state.trades_today > 0:
            return f"{self.ctrl.state.trades_today} trade(s) taken today."
        return ("No high-conviction setups cleared the floor today — a healthy, "
                "disciplined outcome. " + self._conviction(args))

    def _why(self, args) -> str:
        if not args:
            return "usage: /why <trade_id>"
        row = self.journal.conn.execute(
            "SELECT ticker, side, strategy, conviction_score, thesis_id, exit_reason, "
            "pnl_r FROM trades WHERE id=?", (args[0],)).fetchone()
        if not row:
            return f"no trade #{args[0]}"
        t = self.journal.get_thesis(row[4]) if row[4] else None
        mech = t["mechanism"] if t else "(no thesis)"
        return (f"#{args[0]} {row[0]} {row[1]} {row[2]} conv={row[3]:.0f} "
                f"outcome={row[5]} R={row[6]}\n  thesis: {mech}")

    def _thesis(self, args) -> str:
        if not args:
            return "usage: /thesis <id>"
        t = self.journal.get_thesis(args[0])
        if not t:
            return f"no thesis {args[0]}"
        return (f"{t['ticker']} {t['direction']}: {t['claim']}\n  mechanism: "
                f"{t['mechanism']}\n  invalidation: {t['invalidation']}\n  "
                f"confidence {t['confidence']} base_rate {t['base_rate']}")

    def _budget(self, args) -> str:
        if not self.budget:
            return "no budget tracker"
        return (f"LLM today ${self.budget.spent_today():.2f}/"
                f"${self.budget.daily_budget:.2f} | month "
                f"${self.budget.spent_month():.2f}/${self.budget.monthly_budget:.2f} "
                f"| cache {self.budget.cache_hit_rate():.0%}")

    def _help(self, args) -> str:
        return ("CONTROL: /app on|off  /research on|off  /paper on|off  "
                "/trading arm  /trading on|off  /mode\n"
                "INFO: /status /risk /conviction /rejected /why-no-trade "
                "/why <id> /thesis <id> /recommendations /budget\n"
                "ACTIONS: /halt /resume /flatten /strategy <name> on|off")

    # ----- operating-mode command & control ------------------------------ #
    def _mode(self, args) -> str:
        if not self.control:
            return "no control plane wired"
        return self.control.describe()

    def _app(self, args) -> str:
        on = self._onoff(args)
        if on is None or not self.control:
            return "usage: /app on|off"
        return self.control.app(on).message

    def _research(self, args) -> str:
        on = self._onoff(args)
        if on is None or not self.control:
            return "usage: /research on|off"
        return self.control.research(on).message

    def _paper(self, args) -> str:
        on = self._onoff(args)
        if on is None or not self.control:
            return "usage: /paper on|off"
        return self.control.paper(on).message

    def _trading(self, args) -> str:
        if not self.control:
            return "no control plane wired"
        if args and args[0].lower() == "arm":
            r = self.control.arm_trading()
        else:
            on = self._onoff(args)
            if on is None:
                return "usage: /trading arm | /trading on|off"
            r = self.control.trading(on)
        msg = r.message
        if r.blockers:
            msg += "\n  blockers:\n" + "\n".join(f"    - {b}" for b in r.blockers)
        return msg

    def _recommendations(self, args) -> str:
        if not self.journal:
            return "no journal"
        recs = self.journal.recent_recommendations(10)
        if not recs:
            return "no recommendations yet (research mode writes them here)"
        return "\n".join(f"  {r['ts'][:16]} {r['ticker']} {r['side']} {r['strategy']} "
                         f"conv={r['conviction']:.0f} — {r['mechanism'][:60]}" for r in recs)

    # ----- mutating ------------------------------------------------------ #
    def _halt(self, args) -> str:
        self.ctrl.state.halted = True
        self.ctrl.state.halt_reason = "operator /halt"
        return "HALTED by operator. No new entries; open positions remain."

    def _resume(self, args) -> str:
        self.ctrl.state.halted = False
        self.ctrl.state.halt_reason = ""
        return "Resumed. Reconciliation runs before the next entry."

    def _flatten(self, args) -> str:
        n = len(self.ctrl.open)
        self.ctrl._flatten_all({}, "operator", "manual")
        return f"Flattened {n} position(s)."

    def _strategy(self, args) -> str:
        if len(args) < 2 or args[1] not in ("on", "off"):
            return "usage: /strategy <name> on|off"
        name, state = args[0], args[1]
        try:
            rs = self.registry.get(name)
        except KeyError:
            return f"no strategy {name}"
        rs.strategy.activation_status = "paper" if state == "on" else "paused"
        return f"strategy {name} -> {rs.strategy.activation_status}"
