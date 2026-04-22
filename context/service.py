from __future__ import annotations

from sentence_transformers import SentenceTransformer
import numpy as np
from pathlib import Path

from graph import SymbolGraph
from graph.models import Symbol, SymbolDetails, BuildReport
from invalidation import InvalidationEngine
from invalidation.models import ImpactReport
from context.models import FileUpdate, ContextSubgraph
from agents import AgentContextStore
from agents.models import (
    ObservationSource,
    ObservedSymbol,
    StaleContextReport,
    AgentSession,
)


class ContextService:
    def __init__(self, root: Path):
        self.root: Path = root

        self._graph: SymbolGraph = SymbolGraph(root)
        self._engine: InvalidationEngine = InvalidationEngine(self._graph)
        self._symbols: list[Symbol] = []
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._embeddings = None

        self._agents: AgentContextStore = AgentContextStore()

    async def build(self) -> BuildReport:
        await self._graph.build()
        self._refresh()
        return BuildReport(
            root=self.root,
            symbols=self._graph.symbol_count(),
            unresolved_refs=self._graph.unresolved_ref_count(),
        )

    def all_symbols(self) -> list[Symbol]:
        return self._symbols

    def symbol_details(
        self, symbol: str, agent_id: str | None = None
    ) -> SymbolDetails | None:
        if not self._graph.has_symbol(symbol):
            return None

        record: Symbol = self._graph.get_symbol(symbol)
        dependencies: list[Symbol] = [
            self._graph.get_symbol(descendant)
            for descendant in self._graph.descendants(symbol)
        ]
        dependents: list[Symbol] = [
            self._graph.get_symbol(ancestor)
            for ancestor in self._graph.ancestors(symbol)
        ]

        if agent_id is not None:
            self._agents.record_observation(
                agent_id,
                [record, *dependents, *dependencies],
                ObservationSource.SYMBOL_DETAILS,
            )

        return SymbolDetails(
            record=record,
            dependencies=tuple(dependencies),
            dependents=tuple(dependents),
        )

    def symbols_in_file(self, path: Path, agent_id: str | None = None) -> list[Symbol]:
        symbols: list[Symbol] = [
            self._graph.get_symbol(symbol)
            for symbol in self._graph.symbols_in_file(path)
        ]
        if agent_id is not None:
            self._agents.record_observation(
                agent_id, symbols, ObservationSource.FILE_SYMBOLS
            )
        return symbols

    def relevant_symbols_for_task(
        self, task_text: str, limit: int = 10, agent_id: str | None = None
    ) -> list[Symbol]:
        q = self._model.encode([task_text], normalize_embeddings=True)[0]
        scores = self._embeddings @ q
        top = np.argpartition(-scores, min(limit, len(scores) - 1))[:limit]
        top = top[np.argsort(-scores[top])]
        symbols: list[Symbol] = [self._symbols[i] for i in top if scores[i] > 0.2]

        if agent_id is not None:
            self._agents.record_observation(
                agent_id, symbols, ObservationSource.RELEVANT_SYMBOLS
            )

        return symbols

    def subgraph_for_symbols(
        self, symbols: list[str], depth: int = 1, agent_id: str | None = None
    ) -> ContextSubgraph:
        frontier: set[str] = {
            symbol for symbol in symbols if self._graph.has_symbol(symbol)
        }
        visited: set[str] = frontier.copy()

        for _ in range(max(0, depth)):
            expanded: set[str] = frontier.copy()
            for symbol in list(frontier):
                expanded.update(
                    {successor for successor in self._graph.successors(symbol)}
                )
                expanded.update(
                    {ancestor for ancestor in self._graph.ancestors(symbol)}
                )
            frontier = expanded - visited
            visited.update(expanded)

        edges: tuple[tuple[str, str], ...] = tuple(
            sorted((ref.source_symbol, ref.target_symbol) for ref in self._graph.refs())
        )

        if agent_id is not None:
            self._agents.record_observation(
                agent_id,
                [self._graph.get_symbol(symbol) for symbol in visited],
                ObservationSource.SUBGRAPH,
            )

        return ContextSubgraph(
            center_symbols=tuple(symbol for symbol in set(symbols) & visited),
            nodes=tuple(sorted(visited)),
            edges=edges,
        )

    def apply_file_updates(self, updates: list[FileUpdate]) -> ImpactReport:
        changed_symbols: set[str] = self._graph.rebuild_with_overrides(
            {file.path: file.after for file in updates}
        )
        self._refresh()
        return self.invalidate_symbols(changed_symbols)

    def invalidate_symbols(self, changed_symbols: set[str]) -> ImpactReport:
        return self._engine.impacted_symbols(changed_symbols)

    def register_agent(self, name: str, task: str) -> AgentSession:
        return self._agents.register_agent(name, task)

    def record_observation(
        self, agent_id: str, symbols: list[Symbol], source: ObservationSource
    ) -> tuple[ObservedSymbol, ...]:
        return self._agents.record_observation(agent_id, symbols, source)

    def stale_context(self, agent_id: str) -> StaleContextReport:
        return self._agents.stale_context(agent_id, self._graph)

    def affected_agents(self, impacted_symbols: set[str]) -> tuple[AgentSession, ...]:
        return self._agents.affected_agents(impacted_symbols)

    def _refresh(self) -> None:
        self._engine = InvalidationEngine(self._graph)
        self._symbols: list[Symbol] = self._graph.symbol_items()
        self._embeddings = self._model.encode(
            [symbol.summary for symbol in self._symbols],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
