"""
HOOD DaBang — autonomous trading loop (operator's "keep making trades" loop).

Drives the controller on a session-aware cadence. SAFETY by construction:
  - Trades ONLY when the session is tradeable (regular hours by default; extended
    only if explicitly enabled) and the control plane mode is LIVE.
  - Every cycle re-checks killswitches; a halt stops new entries immediately.
  - Every order still routes through the risk gate (deployment cap, per-trade
    cap, conviction floor, thesis requirement) and review_equity_order — the loop
    cannot bypass any of them.
  - Bounded by max_cycles and an explicit `stop` flag so it can never run away.
  - A heartbeat (cheap read) feeds the MCP-outage killswitch (#4).

The loop NEVER self-arms: it runs only while `is_armed()` is true (operator-set).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import market_hours as mh
from ..strategies.base import MarketState
from .. import killswitch as ks


@dataclass
class CycleResult:
    cycle: int
    session: str
    traded: bool
    halted: bool
    reason: str
    trades_today: int


class TradingLoop:
    def __init__(self, controller, *, is_armed: Callable[[], bool],
                 state_provider: Callable[[str], Dict[str, MarketState]],
                 heartbeat: Optional[Callable[[], bool]] = None,
                 now_fn: Callable[[], object] = None,
                 allow_extended: bool = False, audit=None):
        self.ctrl = controller
        self.is_armed = is_armed
        self.state_provider = state_provider
        self.heartbeat = heartbeat or (lambda: True)
        self.now_fn = now_fn or (lambda: None)
        self.allow_extended = allow_extended
        self.audit = audit
        self.stop = False
        self._hb_fail = 0

    def _tradeable_now(self) -> mh.SessionInfo:
        return mh.classify(self.now_fn())

    def run_cycle(self, cycle: int) -> CycleResult:
        info = self._tradeable_now()
        now_et = ""  # the state provider stamps timestamps on the MarketStates

        if not self.is_armed():
            return CycleResult(cycle, info.session, False, False, "not_armed",
                               self.ctrl.state.trades_today)

        # heartbeat -> MCP outage killswitch (#4)
        if not self.heartbeat():
            self._hb_fail += 1
            if self._hb_fail >= 3:
                self.ctrl.state.halted = True
                self.ctrl.state.halt_reason = "#4 mcp_failure: heartbeat lost"
                self._audit("KILL", note="broker_outage_heartbeat")
                return CycleResult(cycle, info.session, False, True,
                                   "mcp_outage_halt", self.ctrl.state.trades_today)
        else:
            self._hb_fail = 0

        if self.ctrl.state.halted:
            return CycleResult(cycle, info.session, False, True,
                               self.ctrl.state.halt_reason, self.ctrl.state.trades_today)

        # session gate: trade only in a tradeable session
        tradeable = info.session == "regular" or (self.allow_extended and info.is_open)
        if not tradeable:
            return CycleResult(cycle, info.session, False, False,
                               f"session_{info.session}_no_trade",
                               self.ctrl.state.trades_today)

        before = self.ctrl.state.trades_today
        states = self.state_provider(now_et)
        if states:
            now = next(iter(states.values())).now_et
            self.ctrl.process_tick(states, now)
        traded = self.ctrl.state.trades_today > before
        return CycleResult(cycle, info.session, traded, self.ctrl.state.halted,
                           "ok", self.ctrl.state.trades_today)

    def run(self, *, max_cycles: int = 1, sleep_s: float = 0.0,
            sleep_fn: Callable[[float], None] = time.sleep) -> List[CycleResult]:
        results: List[CycleResult] = []
        for i in range(max_cycles):
            if self.stop:
                break
            r = self.run_cycle(i)
            results.append(r)
            if r.halted:
                break
            if sleep_s and i < max_cycles - 1:
                sleep_fn(sleep_s)
        return results

    def _audit(self, event, **kw):
        if self.audit is not None:
            self.audit.record(event, **kw)
