from __future__ import annotations

import asyncio
from pathlib import Path
import networkx as nx

from graph.models import (
    Symbol,
    SymbolKind,
    SymbolRef,
    RefKind,
    SymbolTable,
    ParsedFile,
    ResolvedRef,
    UnresolvedRef,
)
from graph.indexer import iter_source_files, is_trackable_source_file
from graph.languages import LanguageAdapter, adapter_for_path


class SymbolGraph:
    def __init__(self, root: Path):
        self.root: Path = root.resolve()
        self._lock = asyncio.Lock()

        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._symbols: SymbolTable = {}
        self._unresolved_refs: list[UnresolvedRef] = []

    async def build(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._build_sync)

    def rebuild_with_overrides(self, overrides: dict[Path, bytes | None]) -> set[str]:
        old_symbols: SymbolTable = self._symbols.copy()
        sources: dict[Path, bytes] = {
            path: path.read_bytes() for path, _ in iter_source_files(self.root)
        }
        normalized: dict[Path, bytes | None] = {}

        for path, content in overrides.items():
            if is_trackable_source_file(path.resolve(), self.root):
                normalized[path.resolve()] = content
        for path, content in normalized.items():
            if content is None:
                sources.pop(path, None)
            else:
                sources[path] = content

        self._g, self._symbols, self._unresolved_refs = self._build_graph_from_sources(
            [
                (path, adapter_for_path(path), src)
                for path, src in sources.items()
                if adapter_for_path(path) is not None
            ]
        )

        changed: set[str] = set()
        for qname, symbol in self._symbols.items():
            if (
                qname not in old_symbols
                or old_symbols.interface_hash != symbol.interface_hash
            ):
                changed.add(qname)
        changed.update(set(old_symbols.keys()) - set(self._symbols.keys()))
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

    def refs(self, **attrs) -> list[ResolvedRef]:
        return [
            ResolvedRef(source_symbol=u, target_symbol=v, **data)
            for u, v, data in self._g.edges(data=True)
            if all(data.get(k) == val for k, val in attrs.items())
        ]

    def symbol_count(self, **attrs) -> int:
        if not attrs:
            return self._g.number_of_nodes()
        return sum(
            1
            for _, d in self._g.nodes(data=True)
            if all(d.get(k) == v for k, v in attrs.items())
        )

    def ref_count(self, **attrs) -> int:
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
        sources: list[tuple[Path, LanguageAdapter, bytes]] = [
            (path, adapter, path.read_bytes())
            for path, adapter in iter_source_files(self.root)
            if adapter is not None
        ]
        graph, symbols, unresolved_refs = self._build_graph_from_sources(sources)
        self._g, self._symbols, self._unresolved_refs = graph, symbols, unresolved_refs

    def _build_graph_from_sources(
        self, sources: list[tuple[Path, LanguageAdapter, bytes]]
    ) -> tuple[nx.MultiDiGraph, SymbolTable, list[UnresolvedRef]]:
        graph: nx.MultiDiGraph = nx.MultiDiGraph()
        symbols: SymbolTable = {}
        unresolved_refs: list[UnresolvedRef] = []
        files: list[ParsedFile] = []

        for path, adapter, source in sources:
            parsed: ParsedFile = adapter.parse_file(path, source, self.root)
            files.append(parsed)
            for symbol in parsed.symbols:
                graph.add_node(symbol.qname)
                symbols[symbol.qname] = symbol

        for parsed in files:
            for ref in parsed.refs:
                resolved, unresolved = self._resolve_ref(ref, parsed, symbols)
                for target in resolved:
                    graph.add_edge(
                        ref.source_symbol,
                        target,
                        kind=ref.kind,
                        module=ref.module,
                        target_name=ref.target_name,
                        recv_name=ref.recv_name,
                    )
                unresolved_refs.extend(unresolved)

            for symbol in parsed.symbols:
                if symbol.parent_qname and symbol.parent_qname in symbols:
                    graph.add_edge(
                        symbol.parent_qname,
                        symbol.qname,
                        kind=RefKind.CONTAINS,
                        module=symbol.module,
                        target_name=symbol.name,
                    )
                elif symbol.parent_qname is not None:
                    unresolved_refs.append(
                        UnresolvedRef(
                            SymbolRef(
                                source_symbol=symbol.parent_qname,
                                target_name=symbol.qname,
                                kind=RefKind.CONTAINS,
                                module=symbol.module,
                            ),
                            reason=f"unrecognized symbol: {symbol.parent_qname}",
                        )
                    )

            for binding in parsed.imports:
                target = binding.target_qname or binding.target_module
                if target and target in symbols:
                    graph.add_edge(
                        parsed.module,
                        target,
                        kind=RefKind.IMPORTS,
                        module=parsed.module,
                        target_name=binding.local_name,
                    )
                else:
                    unresolved_refs.append(
                        UnresolvedRef(
                            ref=SymbolRef(
                                source_symbol=parsed.module,
                                target_name=target,
                                kind=RefKind.IMPORTS,
                                module=parsed.module,
                            ),
                            reason=f"unrecognized symbol: {target}",
                        )
                    )

        return graph, symbols, unresolved_refs

    def _resolve_ref(
        self, ref: SymbolRef, parsed: ParsedFile, symbols: SymbolTable
    ) -> tuple[list[str], list[UnresolvedRef]]:
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
                return ([imported], [])

            same_module: str = f"{parsed.module}.{ref.target_name}"
            if same_module in symbols:
                return ([same_module], [])

        elif ref.recv_name is not None:
            imported_module: str = imported_modules.get(ref.recv_name)
            if imported_module:
                candidate: str = f"{imported_module}.{ref.target_name}"
                if candidate in symbols:
                    return ([candidate], [])

        matches: list[str] = [
            s for s in symbols.keys() if s.rsplit(".", 1)[-1] == ref.target_name
        ]
        if len(matches) == 1:
            return (matches, [])
        elif len(matches) > 1:
            return (
                [],
                [UnresolvedRef(ref=ref, reason=f"ambiguous symbol: {ref.target_name}")],
            )
        else:
            return (
                [],
                [
                    UnresolvedRef(
                        ref=ref, reason=f"unrecognized symbol: {ref.target_name}"
                    )
                ],
            )
