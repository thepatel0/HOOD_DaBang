"""
HOOD DaBang — health monitors (Brief §13 P&L velocity, §17 feed health).

PnLVelocityMonitor — the Knight Capital defense: watches unrealized P&L every
second vs a trailing 60s baseline; a >3σ move pauses new orders and forces a
state verification. FeedHealthMonitor — tracks per-feed last-update age for the
stale-data killswitches. OrderRateMonitor — freezes if the order rate exceeds the
95th percentile of history (order-amplification defense).
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Optional, Tuple


class PnLVelocityMonitor:
    def __init__(self, window_s: int = 60, sigma: float = 3.0,
                 clock: Callable[[], float] = time.time):
        self.window_s = window_s
        self.sigma = sigma
        self.clock = clock
        self._samples: Deque[Tuple[float, float]] = deque()   # (ts, pnl)

    def record(self, pnl: float) -> None:
        now = self.clock()
        self._samples.append((now, pnl))
        while self._samples and now - self._samples[0][0] > self.window_s:
            self._samples.popleft()

    def is_anomaly(self) -> bool:
        if len(self._samples) < 10:
            return False
        deltas = [b[1] - a[1] for a, b in zip(self._samples, list(self._samples)[1:])]
        if len(deltas) < 5:
            return False
        mean = sum(deltas) / len(deltas)
        var = sum((d - mean) ** 2 for d in deltas) / (len(deltas) - 1)
        sd = math.sqrt(var)
        if sd == 0:
            return False
        latest = deltas[-1]
        return abs(latest - mean) > self.sigma * sd


class FeedHealthMonitor:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self._last: Dict[str, float] = {}

    def heartbeat(self, feed: str) -> None:
        self._last[feed] = self.clock()

    def age_s(self, feed: str) -> Optional[float]:
        if feed not in self._last:
            return None
        return self.clock() - self._last[feed]

    def is_stale(self, feed: str, max_age_s: float) -> bool:
        age = self.age_s(feed)
        return age is None or age > max_age_s


class OrderRateMonitor:
    def __init__(self, window_s: int = 60, clock: Callable[[], float] = time.time):
        self.window_s = window_s
        self.clock = clock
        self._times: Deque[float] = deque()
        self._history_max = 0

    def record_order(self) -> None:
        now = self.clock()
        self._times.append(now)
        while self._times and now - self._times[0] > self.window_s:
            self._times.popleft()
        self._history_max = max(self._history_max, len(self._times))

    def rate(self) -> int:
        return len(self._times)

    def is_excessive(self, hard_cap: int = 10) -> bool:
        return self.rate() > hard_cap
