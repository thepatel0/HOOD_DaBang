"""
HOOD DaBang — control plane (operator command & control).

Four independent capabilities the operator flips on/off with simple commands:
  - app       master switch (off => everything off)
  - research  the decision engine runs; with trading off, decisions become
              RECOMMENDATIONS written to memory (or it runs self-tests)
  - paper     isolated paper-trading learning loop (separate data domain)
  - trading   LIVE real-money execution (heavily guarded)

`execution_mode()` tells the controller what to do, by precedence:
  trading -> LIVE | paper -> PAPER | research -> RECOMMEND | else -> IDLE.

Live cannot be enabled without preconditions (eligibility + explicit arm); the
guardrails return clear blockers and leave it OFF. State is persisted so a
restart remembers the mode.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from typing import Callable, List, Optional, Tuple


@dataclass
class ControlState:
    app: bool = False
    research: bool = False
    paper: bool = False
    trading: bool = False         # live
    trading_armed: bool = False   # explicit arm gate for live


@dataclass
class CommandResult:
    ok: bool
    message: str
    blockers: List[str] = field(default_factory=list)


# eligibility_check() -> (eligible_for_live: bool, blockers: list[str])
EligibilityCheck = Callable[[], Tuple[bool, List[str]]]


class ControlPlane:
    def __init__(self, control_path: Optional[str] = None,
                 eligibility_check: Optional[EligibilityCheck] = None):
        self.path = control_path
        self.state = ControlState()
        self.eligibility_check = eligibility_check or (lambda: (False, ["no eligibility check wired"]))
        self.load()

    # ----- persistence --------------------------------------------------- #
    def load(self) -> None:
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path) as fh:
                    self.state = ControlState(**json.load(fh))
            except (ValueError, TypeError):
                self.state = ControlState()

    def save(self) -> None:
        if self.path:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as fh:
                json.dump(asdict(self.state), fh, indent=2)

    # ----- derived state ------------------------------------------------- #
    def execution_mode(self) -> str:
        if not self.state.app:
            return "OFF"
        if self.state.trading:
            return "LIVE"
        if self.state.paper:
            return "PAPER"
        if self.state.research:
            return "RECOMMEND"
        return "IDLE"

    def describe(self) -> str:
        s = self.state
        return (f"app={'on' if s.app else 'off'} research={'on' if s.research else 'off'} "
                f"paper={'on' if s.paper else 'off'} trading={'ON' if s.trading else 'off'}"
                f"{' (armed)' if s.trading_armed else ''} -> mode {self.execution_mode()}")

    # ----- commands ------------------------------------------------------ #
    def app(self, on: bool) -> CommandResult:
        self.state.app = on
        if not on:                       # master off => everything off
            self.state.research = self.state.paper = self.state.trading = False
        self.save()
        return CommandResult(True, f"application {'ON' if on else 'OFF'} — {self.describe()}")

    def research(self, on: bool) -> CommandResult:
        if on and not self.state.app:
            return CommandResult(False, "turn the application on first (/app on)")
        if not on and (self.state.paper or self.state.trading):
            return CommandResult(False, "cannot turn research off while paper/trading "
                                 "are on (they depend on the decision engine)",
                                 ["paper/trading active"])
        self.state.research = on
        self.save()
        return CommandResult(True, f"research {'ON' if on else 'OFF'} — {self.describe()}")

    def paper(self, on: bool) -> CommandResult:
        if on and not self.state.app:
            return CommandResult(False, "turn the application on first (/app on)")
        if on:
            self.state.research = True   # paper implies the decision engine
        self.state.paper = on
        self.save()
        return CommandResult(True, f"paper trading {'ON (isolated sandbox)' if on else 'OFF'} "
                             f"— {self.describe()}")

    def arm_trading(self) -> CommandResult:
        eligible, blockers = self.eligibility_check()
        if not eligible:
            return CommandResult(False, "NOT eligible to arm live trading", blockers)
        self.state.trading_armed = True
        self.save()
        return CommandResult(True, "live trading ARMED. Run /trading on to go live.")

    def trading(self, on: bool) -> CommandResult:
        if not on:
            self.state.trading = False
            self.save()
            return CommandResult(True, f"live trading OFF — {self.describe()}")
        # turning live ON — all guardrails
        if not self.state.app:
            return CommandResult(False, "turn the application on first (/app on)")
        if not self.state.research:
            return CommandResult(False, "turn research on first (/research on)")
        if not self.state.trading_armed:
            return CommandResult(False, "live trading is NOT armed. Run /trading arm "
                                 "first (it checks eligibility).", ["not armed"])
        eligible, blockers = self.eligibility_check()
        if not eligible:
            self.state.trading_armed = False
            return CommandResult(False, "eligibility lost; live trading blocked", blockers)
        self.state.trading = True
        self.save()
        return CommandResult(True, f"LIVE TRADING ON — real capital at risk. {self.describe()}")
