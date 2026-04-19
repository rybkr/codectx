from __future__ import annotations

import logging
import os
from pathlib import Path
import networkx as nx

from graph.indexer import build_graph_from_disk
from graph.languages.base import SymbolDef


log = logging.getLogger("dependency_graph")


class DependencyGraph:
    def __init__(self, root: Path):
        self.root: Path = root
        self._g: nx.DiGraph = nx.DiGraph()
        self._symbols: dict[str, SymbolDef] = {}

    async def build(self) -> None:
        import asyncio

        await asyncio.to_thread(self._build_sync)

    def _build_sync(self) -> None:
        self._g, self._symbols = build_graph_from_disk(self.root)
        log.info(
            "graph built: %d nodes, %d edges",
            self._g.number_of_nodes(),
            self._g.number_of_edges(),
        )

    def dependents(self, symbol: str) -> set[str]:
        if symbol not in self._g:
            return set()
        return nx.ancestors(self._g, symbol)

    def interface_hash(self, symbol: str) -> int | None:
        return self._symbols.get(symbol, {}).get("interface_hash")

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self._symbols

    def symbol_data(self, symbol: str) -> dict | None:
        return self._symbols.get(symbol)

    def symbol_items(self) -> list[tuple[str, dict]]:
        return sorted(self._symbols.items())

    def successors(self, symbol: str) -> list[str]:
        if symbol not in self._g:
            return []
        return sorted(self._g.successors(symbol))

    def edges(self) -> list[tuple[str, str]]:
        return list(self._g.edges())

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def symbols(self) -> list[str]:
        return [symbol for symbol, _ in self.symbol_items()]

    def rebuild_with_overrides(self, overrides: dict[Path, bytes | None]) -> set[str]:
        old_symbols = dict(self._symbols)
        sources = {path: path.read_bytes() for path in _iter_source_files(self.root)}
        normalized: dict[Path, bytes | None] = {}
        for path, content in overrides.items():
            path_obj = path if path.is_absolute() else self.root / path
            if not _is_trackable_source_path(path_obj, self.root):
                continue
            normalized[path_obj] = content
        for path, content in normalized.items():
            if content is None:
                sources.pop(path, None)
            else:
                sources[path] = content

        self._g, self._symbols = _build_graph_from_sources(self.root, sources)
        changed = set()
        for qname, data in self._symbols.items():
            old = old_symbols.get(qname)
            if old is None or old["interface_hash"] != data["interface_hash"]:
                changed.add(qname)
        changed.update(set(old_symbols) - set(self._symbols))
        return changed
