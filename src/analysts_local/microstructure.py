"""
HOOD DaBang — Microstructure Analyst (Tier 0, Brief §5.1).

Rule-based, $0. Computes true time-of-day RVOL (cumulative volume vs the average
cumulative-for-time-of-day), volume-spike flags, options put/call ratio, and the
FINRA short-volume ratio. Options flow is a LEADING EQUITY signal only — we never
trade options; unusual options activity without confirming underlying volume is
downweighted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MicroResult:
    rvol: Optional[float] = None
    volume_spike: bool = False
    put_call_ratio: Optional[float] = None
    short_volume_ratio: Optional[float] = None
    uoa_flag: bool = False              # unusual options activity (confirmation only)
    score: float = 50.0                 # 0-100 microstructure conviction contribution


class MicrostructureAnalyst:
    def analyze(self, *, today_cum_volume: float = None,
                expected_cum_volume: float = None,
                last_bar_volume: float = None, avg_bar_volume: float = None,
                put_volume: float = None, call_volume: float = None,
                short_volume: float = None, total_volume: float = None
                ) -> MicroResult:
        r = MicroResult()

        # true time-of-day RVOL
        if today_cum_volume is not None and expected_cum_volume:
            r.rvol = round(today_cum_volume / expected_cum_volume, 3)

        # volume spike on the latest bar
        if last_bar_volume is not None and avg_bar_volume:
            r.volume_spike = last_bar_volume >= 3.0 * avg_bar_volume

        # options put/call (leading signal only)
        if put_volume is not None and call_volume:
            r.put_call_ratio = round(put_volume / call_volume, 3)
            # bullish UOA = heavy call volume; only meaningful WITH underlying volume
            r.uoa_flag = (r.put_call_ratio < 0.6 and bool(r.volume_spike))

        # FINRA short-volume ratio (dark-pool proxy)
        if short_volume is not None and total_volume:
            r.short_volume_ratio = round(short_volume / total_volume, 3)

        r.score = self._score(r)
        return r

    @staticmethod
    def _score(r: MicroResult) -> float:
        s = 50.0
        if r.rvol is not None:
            s += min(25.0, (r.rvol - 1.0) * 15.0)         # elevated RVOL -> higher
        if r.volume_spike:
            s += 10.0
        if r.uoa_flag:
            s += 8.0                                       # confirmed UOA only
        if r.short_volume_ratio is not None and r.short_volume_ratio > 0.6:
            s += 5.0                                       # heavy short volume = squeeze fuel
        return round(max(0.0, min(100.0, s)), 1)
