"""
HOOD DaBang — reconciliation (Brief §13, §26.9, killswitch #5).

Every 60s (and on every startup/resume before any trade) compare the broker's
positions to our internal mirror. ANY mismatch -> desync -> halt and require
operator confirmation. Trading on a wrong view of our own positions is how small
accounts die.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .mcp_client import RobinhoodMCPClient


@dataclass
class Discrepancy:
    ticker: str
    internal_shares: int
    broker_shares: int
    kind: str            # "share_mismatch" | "missing_at_broker" | "unknown_at_broker"


@dataclass
class ReconResult:
    in_sync: bool
    discrepancies: List[Discrepancy] = field(default_factory=list)

    @property
    def should_halt(self) -> bool:
        return not self.in_sync


class Reconciler:
    def __init__(self, client: RobinhoodMCPClient):
        self.client = client

    def reconcile(self, internal_positions: Dict[str, int]) -> ReconResult:
        """internal_positions: {ticker: shares} from the positions table."""
        broker = {p.ticker: p.shares for p in self.client.get_positions()}
        internal = {t: s for t, s in internal_positions.items() if s != 0}

        diffs: List[Discrepancy] = []
        for ticker in set(internal) | set(broker):
            i = internal.get(ticker, 0)
            b = broker.get(ticker, 0)
            if i == b:
                continue
            if i != 0 and b == 0:
                kind = "missing_at_broker"      # we think we hold it; broker doesn't
            elif i == 0 and b != 0:
                kind = "unknown_at_broker"       # broker holds it; we don't track it
            else:
                kind = "share_mismatch"
            diffs.append(Discrepancy(ticker, i, b, kind))

        return ReconResult(in_sync=(len(diffs) == 0), discrepancies=diffs)
