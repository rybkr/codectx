from __future__ import annotations

from pathlib import Path

from core.models import ContextSubgraph, Symbol, SymbolKind
from graph.dependency_graph import DependencyGraph


class ContextGraph:
    def __init__(self, dependency_graph: DependencyGraph):
        self._graph = dependency_graph

    @property
    def root(self) -> Path:
        return self._graph.root

    @property
    def dependency_graph(self) -> DependencyGraph:
        return self._graph

    async def build(self) -> None:
        await self._graph.build()

    def has_symbol(self, symbol: str) -> bool:
        return self._graph.has_symbol(symbol)

    def symbol(self, symbol: str) -> Symbol | None:
        data = self._graph.symbol_data(symbol)
        if data is None:
            return None
        return Symbol(
            symbol=symbol,
            kind=self._symbol_kind(data.get("kind")),
            interface_hash=data.get("interface_hash"),
        )

    def all_symbols(self) -> list[Symbol]:
        return [
            Symbol(
                symbol=symbol,
                kind=self._symbol_kind(data.get("kind")),
                interface_hash=data.get("interface_hash"),
            )
            for symbol, data in self._graph.symbol_items()
        ]

    def symbols_in_file(self, path: Path | str) -> list[Symbol]:
        module = self._module_name(path)
        return [
            record
            for record in self.all_symbols()
            if record.symbol == module or record.symbol.startswith(f"{module}.")
        ]

    def dependents(self, symbol: str) -> list[Symbol]:
        return [
            self.symbol(dep)
            for dep in sorted(self._graph.dependents(symbol))
            if self.symbol(dep) is not None
        ]

    def dependencies(self, symbol: str) -> list[Symbol]:
        return [
            self.symbol(dep)
            for dep in self._graph.successors(symbol)
            if self.symbol(dep) is not None
        ]

    def subgraph_for_symbols(
        self, symbols: list[str], depth: int = 1
    ) -> ContextSubgraph:
        frontier = {symbol for symbol in symbols if self.has_symbol(symbol)}
        visited = set(frontier)
        for _ in range(max(0, depth)):
            expanded = set(frontier)
            for symbol in list(frontier):
                expanded.update(record.symbol for record in self.dependencies(symbol))
                expanded.update(record.symbol for record in self.dependents(symbol))
            frontier = expanded - visited
            visited.update(expanded)

        edges = tuple(
            sorted(
                (source, target)
                for source, target in self._graph.edges()
                if source in visited and target in visited
            )
        )
        return ContextSubgraph(
            center_symbols=tuple(symbol for symbol in symbols if symbol in visited),
            nodes=tuple(sorted(visited)),
            edges=edges,
        )

    def relevant_symbols_for_task(
        self, task_text: str, limit: int = 12
    ) -> list[Symbol]:
        tokens = {
            token.strip(".,:()[]{}").lower()
            for token in task_text.split()
            if len(token.strip(".,:()[]{}")) >= 3
        }
        scored: list[tuple[int, str]] = []
        for symbol, _ in self._graph.symbol_items():
            haystack = symbol.lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                scored.append((score, symbol))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            self.symbol(symbol) for _, symbol in scored[:limit] if self.symbol(symbol)
        ]

    def invalidate_from_changes(self, changed_symbols: list[str]) -> list[str]:
        impacted = set()
        for symbol in changed_symbols:
            if not self.has_symbol(symbol):
                continue
            impacted.add(symbol)
            impacted.update(self._graph.dependents(symbol))
        return sorted(impacted)

    def _module_name(self, path: Path | str) -> str:
        path_obj = Path(path)
        if not path_obj.is_absolute():
            path_obj = self.root / path_obj
        return ".".join(path_obj.relative_to(self.root).with_suffix("").parts)

    def _symbol_kind(self, raw_kind: object) -> SymbolKind:
        if isinstance(raw_kind, SymbolKind):
            return raw_kind
        try:
            return SymbolKind(str(raw_kind).lower())
        except ValueError:
            return SymbolKind.UNKNOWN
