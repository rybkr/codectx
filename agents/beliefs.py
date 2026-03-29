from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, auto
from pathlib import Path
from typing import Any


class BeliefKind(StrEnum):
    SYMBOL_OBSERVATION = auto()
    TASK_DEPENDENCY = auto()
    FILE_CONTEXT = auto()
    EDIT_TARGET = auto()
    CONTRACT_ASSUMPTION = auto()


class BeliefSource(StrEnum):
    TASK = auto()
    FILE_READ = auto()
    GRAPH = auto()
    SEARCH = auto()
    EDIT_PLAN = auto()
    MANUAL = auto()


@dataclass
class Belief:
    symbol: str
    kind: BeliefKind
    value: Any
    confidence: float = 1.0
    source: BeliefSource = BeliefSource.MANUAL
    is_stale: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class BeliefStore:
    def __init__(self):
        self._store: dict[str, list[Belief]] = {}

    def add(self, belief: Belief) -> None:
        beliefs = self._store.setdefault(belief.symbol, [])
        for existing in beliefs:
            if existing.kind == belief.kind and existing.source == belief.source:
                existing.value = belief.value
                existing.confidence = belief.confidence
                existing.metadata = belief.metadata
                existing.is_stale = belief.is_stale
                return
        beliefs.append(belief)

    def get(self, symbol: str) -> list[Belief]:
        return self._store.get(symbol, [])

    def symbols(self) -> set[str]:
        return set(self._store)

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self._store

    def mark_stale(self, symbol: str) -> None:
        for belief in self._store.get(symbol, []):
            belief.is_stale = True

    def refresh(
        self,
        symbol: str,
        kind: BeliefKind,
        new_value: Any,
        *,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        for belief in self._store.get(symbol, []):
            if belief.kind == kind:
                belief.value = new_value
                belief.is_stale = False
                if confidence is not None:
                    belief.confidence = confidence
                if metadata is not None:
                    belief.metadata = metadata

    def stale_symbols(self) -> list[str]:
        return [
            symbol
            for symbol, beliefs in self._store.items()
            if any(belief.is_stale for belief in beliefs)
        ]

    def all(self) -> dict[str, list[Belief]]:
        return {symbol: list(beliefs) for symbol, beliefs in self._store.items()}


def module_symbol_for_path(path: Path, root: Path | None = None) -> str:
    if root is not None:
        path = path.relative_to(root)
    return ".".join(path.with_suffix("").parts)
