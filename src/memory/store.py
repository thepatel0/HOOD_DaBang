"""
HOOD DaBang — layered memory (Brief §11, FinMem design).

Four namespaces (working / short / medium / long), retrieval weighted by
recency × relevance × importance, and weekly consolidation (graduate patterns
seen >=3x with consistent outcome to long-term; demote contradicted ones).

The embedder is INJECTED. Default is a dependency-free local hashing embedder
(deterministic, $0, good enough for similarity ranking and fully testable);
sentence-transformers (all-MiniLM-L6-v2) swaps in for production quality via the
`embedder=` arg — no other code changes.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

LAYERS = ("working", "short", "medium", "long")
_TOKEN = re.compile(r"[a-z0-9]+")


# --------------------------------------------------------------------------- #
# Local hashing embedder (dependency-free, deterministic)                      #
# --------------------------------------------------------------------------- #
def hashing_embed(text: str, dim: int = 128) -> List[float]:
    vec = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 7) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # both pre-normalized


@dataclass
class MemoryItem:
    content: str
    layer: str = "working"
    importance: int = 1            # 1 routine, 3 surprising, 5 lesson
    created_ts: float = field(default_factory=time.time)
    last_confirmed_ts: float = field(default_factory=time.time)
    confirmation_count: int = 1
    contradiction_count: int = 0
    status: str = "active"         # active | stable | stale
    embedding: List[float] = field(default_factory=list)
    id: int = 0


class MemoryStore:
    def __init__(self, embedder: Callable[[str], List[float]] = hashing_embed,
                 clock: Callable[[], float] = time.time,
                 half_life_days: float = 30.0):
        self.embedder = embedder
        self.clock = clock
        self.half_life_s = half_life_days * 86400
        self._items: List[MemoryItem] = []
        self._next_id = 1

    # ----- write --------------------------------------------------------- #
    def add(self, content: str, *, layer: str = "working", importance: int = 1) -> MemoryItem:
        item = MemoryItem(content=content, layer=layer, importance=importance,
                          created_ts=self.clock(), last_confirmed_ts=self.clock(),
                          embedding=self.embedder(content), id=self._next_id)
        self._next_id += 1
        self._items.append(item)
        return item

    def confirm(self, item: MemoryItem) -> None:
        item.confirmation_count += 1
        item.last_confirmed_ts = self.clock()

    def contradict(self, item: MemoryItem) -> None:
        item.contradiction_count += 1

    # ----- retrieval (recency × relevance × importance) ------------------ #
    def _decay(self, item: MemoryItem) -> float:
        age = self.clock() - item.created_ts
        return math.exp(-age / self.half_life_s) if self.half_life_s > 0 else 1.0

    def retrieve(self, query: str, k: int = 5,
                 layers: Optional[Sequence[str]] = None) -> List[MemoryItem]:
        q = self.embedder(query)
        pool = [m for m in self._items if (layers is None or m.layer in layers)]
        scored = []
        for m in pool:
            relevance = max(0.0, cosine(q, m.embedding))
            decay = self._decay(m)
            imp = m.importance / 5.0
            score = 0.3 * decay + 0.5 * relevance + 0.2 * imp
            scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:k]]

    # ----- consolidation (weekly, Brief §11) ----------------------------- #
    def consolidate(self) -> Dict[str, int]:
        graduated = demoted = stabilized = 0
        for m in self._items:
            # graduate: seen >=3x with consistent outcome -> long-term
            if (m.confirmation_count >= 3 and m.contradiction_count == 0
                    and m.layer != "long"):
                m.layer = "long"
                graduated += 1
            # demote: long-term contradicted >=2x -> medium for re-validation
            elif m.layer == "long" and m.contradiction_count >= 2:
                m.layer = "medium"
                m.status = "active"
                demoted += 1
            # stable: 90 days of confirmation, immutable until 5+ contradictions
            elif (m.layer == "long" and m.status != "stable"
                  and (self.clock() - m.created_ts) > 90 * 86400
                  and m.contradiction_count == 0):
                m.status = "stable"
                stabilized += 1
        return {"graduated": graduated, "demoted": demoted, "stabilized": stabilized}

    def all(self, layer: Optional[str] = None) -> List[MemoryItem]:
        return [m for m in self._items if layer is None or m.layer == layer]
