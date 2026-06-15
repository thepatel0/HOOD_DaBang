"""
HOOD DaBang — Insider/Institutional Analyst (Tier 0, Brief §5.1).

Threshold rules over SEC EDGAR Form 4 transactions (parsed JSON, no LLM). Flags:
cluster insider buying (>=3 distinct insiders buying in 30 days), large buys
(>$500K or >1% of an insider's holdings), and large CEO/CFO sells (>$5M). Insider
BUYS are weakly bullish (more signal than sells, which are noisy).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Form4Txn:
    insider: str
    role: str                  # "CEO" | "CFO" | "Director" | ...
    side: str                  # "buy" | "sell"
    dollars: float
    pct_of_holdings: float = 0.0
    days_ago: int = 0


@dataclass
class InsiderResult:
    cluster_buy: bool = False
    n_buyers_30d: int = 0
    large_buy: bool = False
    large_exec_sell: bool = False
    score: float = 50.0        # 0-100 (insider conviction contribution)
    flags: List[str] = field(default_factory=list)


class InsiderAnalyst:
    def analyze(self, txns: List[Form4Txn]) -> InsiderResult:
        r = InsiderResult()
        recent = [t for t in txns if t.days_ago <= 30]
        buyers = {t.insider for t in recent if t.side == "buy"}
        r.n_buyers_30d = len(buyers)

        if len(buyers) >= 3:
            r.cluster_buy = True
            r.flags.append("cluster_insider_buy")

        for t in recent:
            if t.side == "buy" and (t.dollars > 500_000 or t.pct_of_holdings > 0.01):
                r.large_buy = True
                r.flags.append("large_insider_buy")
                break
        for t in recent:
            if (t.side == "sell" and t.role in ("CEO", "CFO") and t.dollars > 5_000_000):
                r.large_exec_sell = True
                r.flags.append("large_exec_sell")
                break

        r.score = self._score(r)
        return r

    @staticmethod
    def _score(r: InsiderResult) -> float:
        s = 50.0
        if r.cluster_buy:
            s += 15.0
        if r.large_buy:
            s += 10.0
        if r.large_exec_sell:
            s -= 20.0           # executive selling is a meaningful negative
        # incremental credit for more buyers
        s += min(10.0, max(0, r.n_buyers_30d - 1) * 3.0)
        return round(max(0.0, min(100.0, s)), 1)
