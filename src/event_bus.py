"""
HOOD DaBang — event bus (Brief 4.2).

In-process priority FIFO. KillEvent jumps ahead of everything; otherwise events
are strict FIFO within priority. Pure stdlib (heapq) so it runs anywhere, $0.

The event taxonomy is ordered by priority (lower number == higher priority).
"""
from __future__ import annotations

import heapq
import itertools
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


# Priority ladder (Brief 4.2). KillEvent is top; HeartbeatEvent is bottom.
PRIORITY = {
    "KillEvent": 0,
    "FillEvent": 1,
    "ReconciliationEvent": 2,
    "RiskDecisionEvent": 3,
    "OrderEvent": 4,
    "ConvictionEvent": 5,
    "TradePlanEvent": 6,
    "InsightEvent": 7,
    "ResearchEvent": 8,
    "SignalEvent": 9,
    "NewsEvent": 10,
    "MarketDataEvent": 11,
    "RegimeChangeEvent": 12,
    "HeartbeatEvent": 99,
}


@dataclass
class Event:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.type, 50)


class EventBus:
    """Priority FIFO. KillEvent always dequeues first regardless of insertion
    order; ties broken by insertion order (a monotonic counter), giving FIFO
    within each priority class."""

    def __init__(self) -> None:
        self._heap: List[tuple] = []
        self._counter = itertools.count()
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}

    def publish(self, event: Event) -> None:
        if event.type not in PRIORITY:
            raise ValueError(f"unknown event type: {event.type!r}")
        heapq.heappush(self._heap, (event.priority, next(self._counter), event))

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def pop(self) -> Event | None:
        """Return the highest-priority (then earliest) event, or None if empty."""
        if not self._heap:
            return None
        return heapq.heappop(self._heap)[2]

    def __len__(self) -> int:
        return len(self._heap)

    def dispatch_once(self) -> Event | None:
        """Pop one event and deliver to its subscribers. Returns the event."""
        ev = self.pop()
        if ev is None:
            return None
        for handler in self._subscribers.get(ev.type, []):
            handler(ev)
        return ev

    def drain(self, max_events: int = 10_000) -> int:
        """Dispatch until empty (or max_events). Returns count dispatched.
        A handler may publish new events; KillEvents published mid-drain still
        jump the queue and are delivered before lower-priority pending work."""
        n = 0
        while self._heap and n < max_events:
            self.dispatch_once()
            n += 1
        return n
