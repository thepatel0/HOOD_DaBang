"""
HOOD DaBang — operational lifecycle (Brief §23, §26.11).

Startup gating (the order is load-bearing): refuse if HALT.flag present -> run
self-tests -> reconcile broker vs internal -> only then clear to trade. Any
failure halts and asks the operator. Plus a launchd plist generator for the
7:15 ET auto-start.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import selftest
from ..reconciliation import Reconciler


@dataclass
class StartupResult:
    can_trade: bool
    blockers: List[str] = field(default_factory=list)
    selftest_summary: str = ""


def startup_checks(*, project_dir: str, cfg: dict,
                   reconciler: Optional[Reconciler] = None,
                   internal_positions: Optional[Dict[str, int]] = None,
                   run_selftests: bool = True) -> StartupResult:
    blockers: List[str] = []

    # 1) HALT.flag -> refuse to start (Brief §23.2/§23.6)
    if os.path.exists(os.path.join(project_dir, "HALT.flag")):
        blockers.append("HALT.flag present — operator must remove it")

    # 2) self-tests (killswitch #15)
    summary = ""
    if run_selftests:
        report = selftest.run(cfg)
        summary = report.summary()
        if not report.all_passed:
            blockers.append(f"self-tests failed: {[r.name for r in report.failures]}")

    # 3) reconciliation before any trade (#5)
    if reconciler is not None and internal_positions is not None:
        recon = reconciler.reconcile(internal_positions)
        if recon.should_halt:
            blockers.append(f"reconciliation desync: "
                            f"{[d.ticker for d in recon.discrepancies]}")

    return StartupResult(can_trade=(len(blockers) == 0), blockers=blockers,
                         selftest_summary=summary)


def generate_launchd_plist(user: str, project_dir: str = None,
                           hour: int = 7, minute: int = 15) -> str:
    project_dir = project_dir or f"/Users/{user}/hood-dabang"
    py = f"{project_dir}/.venv/bin/python"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.hooddabang.controller</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py}</string>
        <string>-m</string><string>src.run_live</string>
    </array>
    <key>WorkingDirectory</key><string>{project_dir}</string>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
    <key>RunAtLoad</key><false/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/><key>Crashed</key><true/></dict>
    <key>StandardOutPath</key><string>{project_dir}/logs/launchd.out.log</string>
    <key>StandardErrorPath</key><string>{project_dir}/logs/launchd.err.log</string>
</dict>
</plist>
"""
