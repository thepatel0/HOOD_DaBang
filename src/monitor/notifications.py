"""
HOOD DaBang — notifications (Brief §21).

macOS native notifications via osascript (no extra deps). Anti-fatigue: routine
events are 'quiet'; only material events (stop hit, halt, target reached, budget
breach) are loud. The shell runner is injectable so this is testable without
actually firing a desktop notification.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable, List, Optional


# Events the operator should always hear (loud); everything else is quiet.
LOUD_EVENTS = {
    "daily_loss_hit", "drawdown_halt", "catastrophic_halt", "mcp_disconnect",
    "self_test_failure", "pnl_velocity_anomaly", "llm_budget_hit", "stop_hit",
    "unhedged_position", "reconciliation_desync",
}


@dataclass
class Notification:
    event: str
    title: str
    message: str
    loud: bool
    sound: str


class Notifier:
    def __init__(self, runner: Optional[Callable[[List[str]], None]] = None,
                 enabled: bool = True):
        # runner(argv) executes the command; default uses subprocess.
        self.runner = runner or self._default_runner
        self.enabled = enabled
        self.sent: List[Notification] = []

    @staticmethod
    def _default_runner(argv: List[str]) -> None:
        import subprocess
        subprocess.run(argv, check=False)

    def notify(self, event: str, title: str, message: str,
               sound: Optional[str] = None) -> Notification:
        loud = event in LOUD_EVENTS
        snd = sound or ("Glass" if loud else "")
        n = Notification(event, title, message, loud, snd)
        self.sent.append(n)
        if self.enabled:
            script = f'display notification {self._q(message)} with title {self._q(title)}'
            if snd:
                script += f' sound name {self._q(snd)}'
            self.runner(["osascript", "-e", script])
        return n

    @staticmethod
    def _q(s: str) -> str:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
