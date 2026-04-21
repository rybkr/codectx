from __future__ import annotations

import asyncio
from pathlib import Path
import networkx as nx

from graph.models import Symbol, SymbolKind, SymbolRef, RefKind, SymbolTable
from graph.indexer import iter_source_files


class SymbolGraph:
    def __init__(self, root: Path):
        self.root: Path = root.resolve()
        self._lock = asyncio.Lock()

        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._symbols: SymbolTable = {}

    async def build(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._build_sync)

    def rebuild_with_overrides(self, overrides: dict[Path, bytes | None]) -> set[str]:
        old_symbols: SymbolTable = self._symbols.copy()
        sources: dict[Path:bytes] = {
            path: path.read_bytes() for path in iter_source_files(self.root)
        }
        normalized: dict[Path : bytes | None] = {}

        for path, content in overrides.items():
            if is_trackable_source_file(path.resolve(), self.root):
                normalized[path.resolve()] = content
        for path, content in normalized.items():
            if content is None:
                sources.pop(path, None)
            else:
                sources[path] = content

        self._g, self._symbols = self._build_graph_from_sources(self.root, sources)

        changed: set[str] = set()
        for qname, symbol in self._symbols.items():
            if (
                qname not in old_symbols
                or old_symbols.interface_hash != symbol.interface_hash
            ):
                changed.add(qname)
        changed.update(self(old_symbols.keys()) - set(self._symbols.keys()))
        return changed

    def has_symbol(self, qname: str) -> bool:
        return qname in self._symbols

    def get_symbol(self, qname: str) -> Symbol | None:
        return self._symbols.get(qname, None)

    def symbols(self, kinds: set[SymbolKind] | None = None) -> list[str]:
        return [
            qname
            for qname, symbol in self._symbols.items()
            if kinds is None or symbol.kind in kinds
        ]

    def symbol_items(self, kinds: set[SymbolKind] | None = None) -> list[Symbol]:
        return [
            symbol
            for symbol in self._symbols.values()
            if kinds is None or symbol.kind in kinds
        ]

    def symbols_in_file(self, path: Path) -> list[str]:
        return [
            symbol
            for symbol in self._symbols.values()
            if symbol.path == path.resolve()
        ]

    def edges(self, **attrs) -> list[SymbolRef]:
        return [
            SymbolRef(source_symbol=u, target_name=v, **data)
            for u, v, data in self._g.edges(data=True)
            if all(data.get(k) == val for k, val in attrs.items())
        ]

    def node_count(self, **attrs) -> int:
        if not attrs:
            return self._g.number_of_nodes()
        return sum(
            1
            for _, d in self._g.nodes(data=True)
            if all(d.get(k) == v for k, v in attrs.items())
        )

    def edge_count(self, **attrs) -> int:
        if not attrs:
            return self._g.number_of_edges()
        return sum(
            1
            for *_, d in self._g.edges(data=True)
            if all(d.get(k) == v for k, v in attrs.items())
        )

    def successors(self, qname: str, **attrs) -> list[str]:
        seen: set[str] = set()
        for _, v, data in self._g.out_edges(qname, data=True):
            if all(data.get(k) == val for k, val in attrs.items()) and v not in seen:
                seen.add(v)
        return sorted(seen)

    def descendants(self, qname: str, **attrs) -> list[str]:
        if not attrs:
            return sorted(nx.descendants(self._g, qname))
        seen: set[str] = set()
        stack = [qname]
        while stack:
            node = stack.pop()
            for _, v, data in self._g.out_edges(node, data=True):
                if (
                    all(data.get(k) == val for k, val in attrs.items())
                    and v not in seen
                ):
                    seen.add(v)
                    stack.append(v)
        return sorted(seen)

    def ancestors(self, qname: str, **attrs) -> list[str]:
        if not attrs:
            return sorted(nx.ancestors(self._g, qname))
        seen: set[str] = set()
        stack = [qname]
        while stack:
            node = stack.pop()
            for u, _, data in self._g.in_edges(node, data=True):
                if (
                    all(data.get(k) == val for k, val in attrs.items())
                    and u not in seen
                ):
                    seen.add(u)
                    stack.append(u)
        return sorted(seen)

    def children(self, qname: str) -> list[str]:
        return self.successors(qname, kind=RefKind.CONTAINS)

    def parent(self, qname: str) -> str | None:
        parents = [
            u
            for u, _, data in self._g.in_edges(qname, data=True)
            if data.get("kind") == RefKind.CONTAINS
        ]
        if not parents:
            return None
        if len(parents) > 1:
            raise ValueError(f"{qname} has multiple parents: {parents}")
        return parents[0]

    def _build_sync(self) -> None:
        graph, symbols = self._build_graph_from_sources()
        self._g, self._symbols = graph, symbols

    def _build_graph_from_sources(self) -> tuple[nx.MultiDiGraph, SymbolTable]:
        graph: nx.MultiDiGraph = nx.MultiDiGraph()
        symbols: SymbolTable = {}

        sources: list[tuple[Path, LanguageAdapter, bytes]] = [
            (path, adapter, path.read_bytes())
            for path, adapter in iter_source_files(self.root)
        ]
        files: list[ParsedFile] = []

        for path, adapter, source in sources:
            parsed: ParsedFile = adapter.parse_file(path, source, self.root)
            files.append(parsed)
            for symbol in parsed.symbols:
                graph.add_node(symbol.qname)
                symbols[symbol.qname] = symbol

        for parsed in files:
            for ref in parsed.refs:
                for target in self._resolve_ref(ref, parsed, symbols):
                    graph.add_edge(ref.source_symbol, target, kind=ref.kind)

            for symbol in parsed.symbols:
                if symbol.parent and symbol.parent in symbols:
                    graph.add_edge(symbol.parent, symbol.qname, kind=RefKind.CONTAINS)

            for binding in parsed.imports:
                target = binding.target_qname or binding.target_module
                if target and target in symbols:
                    graph.add_edge(parsed.module, target, kind=RefKind.IMPORTS)

        return graph, symbols

    def _resolve_ref(
        self, ref: SymbolRef, parsed: ParsedFile, symbols: SymbolTable
    ) -> list[str]:
        imported_symbols: dict[str, str] = {
            binding.local_name: binding.target_qname
            for binding in parsed.imports
            if binding.target_qname is not None
        }
        imported_modules: dict[str, str] = {
            binding.local_name: binding.target_module
            for binding in parsed.imports
            if binding.target_module is not None
        }

        if ref.recv_name is None:
            imported: str = imported_symbols.get(ref.target_name)
            if imported and imported in symbols:
                return [imported]

            same_module: str = f"{parsed.module}.{ref.target_name}"
            if same_module in symbols:
                return [same_module]

        elif ref.recv_name is not None:
            imported_module: str = imported_modules.get(ref.recv_name)
            if imported_module:
                candidate: str = f"{imported_module}.{ref.target_name}"
                if candidate in symbols:
                    return [candidate]

        matches: list[str] = [
            s for s in symbols.keys() if s.rsplit(".", 1)[-1] == ref.target_name
        ]
        return matches if len(matches) == 1 else []
