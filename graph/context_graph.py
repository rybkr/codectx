from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from graph.dependency_graph import DependencyGraph


@dataclass(frozen=True)
class SymbolRecord:
    symbol: str
    kind: str
    interface_hash: int | None


@dataclass(frozen=True)
class ContextSubgraph:
    center_symbols: tuple[str, ...]
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]


class ContextGraph:
    def __init__(self, dependency_graph: DependencyGraph):
        self._graph = dependency_graph

    @property
    def root(self) -> Path:
        return self._graph.root

    async def build(self) -> None:
        await self._graph.build()

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self._graph._symbols

    def symbol(self, symbol: str) -> SymbolRecord | None:
        data = self._graph._symbols.get(symbol)
        if data is None:
            return None
        return SymbolRecord(
            symbol=symbol,
            kind=str(data.get("kind", "unknown")),
            interface_hash=data.get("interface_hash"),
        )

    def all_symbols(self) -> list[SymbolRecord]:
        return [
            SymbolRecord(
                symbol=symbol,
                kind=str(data.get("kind", "unknown")),
                interface_hash=data.get("interface_hash"),
            )
            for symbol, data in sorted(self._graph._symbols.items())
        ]

    def symbols_in_file(self, path: Path | str) -> list[SymbolRecord]:
        module = self._module_name(path)
        return [
            record
            for record in self.all_symbols()
            if record.symbol == module or record.symbol.startswith(f"{module}.")
        ]

    def dependents(self, symbol: str) -> list[SymbolRecord]:
        return [
            self.symbol(dep)
            for dep in sorted(self._graph.dependents(symbol))
            if self.symbol(dep)
        ]

    def dependencies(self, symbol: str) -> list[SymbolRecord]:
        successors = (
            sorted(self._graph._g.successors(symbol)) if self.has_symbol(symbol) else []
        )
        return [self.symbol(dep) for dep in successors if self.symbol(dep)]

    def neighbors(self, symbol: str) -> list[SymbolRecord]:
        seen = {
            record.symbol: record
            for record in [*self.dependencies(symbol), *self.dependents(symbol)]
            if record is not None
        }
        return [seen[key] for key in sorted(seen)]

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
                for source, target in self._graph._g.edges()
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
    ) -> list[SymbolRecord]:
        tokens = {
            token.strip(".,:()[]{}").lower()
            for token in task_text.split()
            if len(token.strip(".,:()[]{}")) >= 3
        }
        scored: list[tuple[int, str]] = []
        for symbol in self._graph._symbols:
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
