"""
HOOD DaBang — run environments (DATA ISOLATION).

A RunEnvironment owns ALL paths for one isolation domain. Production and Paper
get entirely separate roots so their databases, journals, memory, and ledgers can
NEVER share a file. This is the operator's hard requirement: paper-trading data
is completely isolated from production and never mixes.

Only the shared KnowledgeBase (validated patterns with provenance) crosses the
boundary — and only AFTER a pattern survives falsification (see knowledge.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RunEnvironment:
    name: str                  # "production" | "paper"
    root: str                  # absolute base directory for this domain

    @property
    def is_paper(self) -> bool:
        return self.name == "paper"

    @property
    def db_path(self) -> str:
        return os.path.join(self.root, "trader.db")

    @property
    def ledger_path(self) -> str:
        return os.path.join(self.root, "llm_ledger.db")

    @property
    def memory_dir(self) -> str:
        return os.path.join(self.root, "memory")

    @property
    def journal_dir(self) -> str:
        return os.path.join(self.root, "journal")

    @property
    def recommendations_dir(self) -> str:
        return os.path.join(self.root, "recommendations")

    def ensure_dirs(self) -> None:
        for d in (self.root, self.memory_dir, self.journal_dir,
                  self.recommendations_dir):
            os.makedirs(d, exist_ok=True)

    # ----- factories ----------------------------------------------------- #
    @classmethod
    def production(cls, base: str) -> "RunEnvironment":
        # base is the project's data/ directory
        return cls("production", os.path.join(base, "prod"))

    @classmethod
    def paper(cls, base: str) -> "RunEnvironment":
        return cls("paper", os.path.join(base, "paper"))

    def assert_isolated_from(self, other: "RunEnvironment") -> None:
        """Guarantee two environments share no paths (called at startup)."""
        if os.path.abspath(self.root) == os.path.abspath(other.root):
            raise RuntimeError(
                f"environment isolation violated: {self.name} and {other.name} "
                f"share root {self.root}")
