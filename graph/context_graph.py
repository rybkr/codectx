from __future__ import annotations

from sentence_transformers import SentenceTransformer
import numpy as np
from dataclasses import dataclass

from graph.models import Symbol
from graph.symbol_graph import SymbolGraph


@dataclass(frozen=True)
class ContextSubgraph:
    center_symbols: tuple[str, ...]
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]


class ContextGraph:
    def __init__(self, symbol_graph: SymbolGraph):
        self._graph = symbol_graph
        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._symbols: list[Symbol] = self._graph.symbol_items()
        self._embeddings = self._model.encode(
            [symbol.summary for symbol in self._symbols],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def __getattr__(self, name):
        return getattr(self._graph, name)

    def relevant_symbols(self, task_text: str, limit: int = 10) -> list[Symbol]:
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
                    {record.qname for record in self._graph.sucessors(symbol)}
                )
                expanded.update(
                    {record.qname for record in self._graph.dependents(symbol)}
                )
            frontier = expanded - visited
            visited.update(expanded)

        edges: tuple[tuple[str, str], ...] = tuple(
            sorted((ref.source_symbol, ref.target_name) for ref in self._graph.refs)
        )
        return ContextSubgraph(
            center_symbols=tuple(symbol for symbol in set(symbols) & visited),
            nodes=tuple(sorted(visited)),
            edges=edges,
        )
