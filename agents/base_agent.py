from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable

from agents.beliefs import (
    Belief,
    BeliefKind,
    BeliefSource,
    BeliefStore,
    module_symbol_for_path,
)
from graph.context_graph import ContextGraph


class BaseAgent(ABC):
    def __init__(self, id: int, cfg: dict, context_graph: ContextGraph | None = None):
        self.id: int = id
        self.cfg: dict = cfg
        self.context_graph = context_graph
        self.beliefs = BeliefStore()
        self._inbox: asyncio.Queue = asyncio.Queue()

    async def receive_invalidation(
        self, symbol: str, kind: str, new_value: Any
    ) -> None:
        await self._inbox.put((symbol, kind, new_value))

    async def _drain_inbox(self) -> None:
        while not self._inbox.empty():
            symbol, kind, new_value = self._inbox.get_nowait()
            if kind == "symbol_stale":
                self.beliefs.mark_stale(symbol)

    def observe_symbols(
        self,
        symbols: Iterable[str],
        *,
        source: BeliefSource = BeliefSource.MANUAL,
        kind: BeliefKind = BeliefKind.SYMBOL_OBSERVATION,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        for symbol in symbols:
            self.beliefs.add(
                Belief(
                    symbol=symbol,
                    kind=kind,
                    value={"observed": True},
                    confidence=confidence,
                    source=source,
                    metadata=metadata or {},
                )
            )

    def declare_task_dependencies(
        self,
        symbols: Iterable[str],
        *,
        confidence: float = 1.0,
    ) -> None:
        self.observe_symbols(
            symbols,
            source=BeliefSource.TASK,
            kind=BeliefKind.TASK_DEPENDENCY,
            confidence=confidence,
        )

    def declare_edit_targets(
        self,
        symbols: Iterable[str],
        *,
        confidence: float = 1.0,
    ) -> None:
        self.observe_symbols(
            symbols,
            source=BeliefSource.EDIT_PLAN,
            kind=BeliefKind.EDIT_TARGET,
            confidence=confidence,
        )

    def observe_contracts(
        self,
        symbols: Iterable[str],
        *,
        source: BeliefSource = BeliefSource.MANUAL,
        confidence: float = 1.0,
    ) -> None:
        self.observe_symbols(
            symbols,
            source=source,
            kind=BeliefKind.CONTRACT_ASSUMPTION,
            confidence=confidence,
        )

    def observe_file(
        self,
        path: Path,
        *,
        root: Path | None = None,
        symbols: Iterable[str] = (),
        confidence: float = 1.0,
    ) -> None:
        file_symbol = module_symbol_for_path(path, root)
        self.beliefs.add(
            Belief(
                symbol=file_symbol,
                kind=BeliefKind.FILE_CONTEXT,
                value={"path": str(path)},
                confidence=confidence,
                source=BeliefSource.FILE_READ,
            )
        )
        if symbols:
            self.observe_symbols(
                symbols,
                source=BeliefSource.FILE_READ,
                kind=BeliefKind.SYMBOL_OBSERVATION,
                confidence=confidence,
                metadata={"path": str(path)},
            )

    def query_relevant_symbols(self, task_text: str, limit: int = 12) -> list[str]:
        if self.context_graph is None:
            return []
        return [
            record.symbol
            for record in self.context_graph.relevant_symbols_for_task(
                task_text, limit=limit
            )
        ]

    def query_file_symbols(self, path: Path | str) -> list[str]:
        if self.context_graph is None:
            return []
        return [record.symbol for record in self.context_graph.symbols_in_file(path)]

    @abstractmethod
    async def run(self) -> None:
        pass
