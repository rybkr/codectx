from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContextSubgraph:
    center_symbols: tuple[str, ...]
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]

    @property
    def payload(self) -> dict[str, object]:
        return {
            "center_symbols": self.center_symbols,
            "nodes": self.nodes,
            "edges": self.edges,
        }


@dataclass(frozen=True)
class FileUpdate:
    path: Path
    before: bytes
    after: bytes
