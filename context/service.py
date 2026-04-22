from __future__ import annotations

from sentence_transformers import SentenceTransformer
import numpy as np
from pathlib import Path

from graph import SymbolGraph
from graph.models import Symbol, SymbolDetails, BuildReport
from invalidation import InvalidationEngine
from invalidation.models import ImpactReport
from context.models import FileUpdate, ContextSubgraph


class ContextService:
    def __init__(self, root: Path):
        self.root: Path = root

        self._graph: SymbolGraph = SymbolGraph(root)
        self._engine: InvalidationEngine = InvalidationEngine(self._graph)
        self._symbols: list[Symbol] = []
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._embeddings = None

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

    def symbol_details(self, symbol: str) -> SymbolDetails | None:
        if not self._graph.has_symbol(symbol):
            return None
        return SymbolDetails(
            record=self._graph.get_symbol(symbol),
            dependencies=tuple(
                [
                    self._graph.get_symbol(descendant)
                    for descendant in self._graph.descendants(symbol)
                ]
            ),
            dependents=tuple(
                [
                    self._graph.get_symbol(ancestor)
                    for ancestor in self._graph.ancestors(symbol)
                ]
            ),
        )

    def symbols_in_file(self, path: Path) -> list[Symbol]:
        return [
            self._graph.get_symbol(symbol)
            for symbol in self._graph.symbols_in_file(path)
        ]

    def relevant_symbols_for_task(
        self, task_text: str, limit: int = 10
    ) -> list[Symbol]:
        q = self._model.encode([task_text], normalize_embeddings=True)[0]
        scores = self._embeddings @ q
        top = np.argpartition(-scores, min(limit, len(scores) - 1))[:limit]
        top = top[np.argsort(-scores[top])]
        return [self._symbols[i] for i in top if scores[i] > 0.2]

    def subgraph_for_symbols(
        self, symbols: list[str], depth: int = 1
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

    def _refresh(self) -> None:
        self._engine = InvalidationEngine(self._graph)
        self._symbols: list[Symbol] = self._graph.symbol_items()
        self._embeddings = self._model.encode(
            [symbol.summary for symbol in self._symbols],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
