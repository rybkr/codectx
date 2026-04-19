from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.models import EditResult, SymbolKind, RefKind


@dataclass(frozen=True)
class SymbolDef:
    qname: str
    kind: SymbolKind
    interface_hash: int | None


@dataclass(frozen=True)
class SymbolRef:
    source_symbol: str
    target_name: str
    kind: RefKind


@dataclass(frozen=True)
class ParsedFile:
    module: str
    symbols: list[SymbolDef]
    refs: list[SymbolRef]


class LanguageAdapter(Protocol):
    name: str

    def supports_path(self, path: Path) -> bool: ...

    def module_name(self, path: Path, root: Path) -> str: ...

    def parse_file(self, Path: Path, source: bytes, root: Path) -> ParsedFile: ...

    def classify_edits(
        self, old_src: bytes, new_src: bytes, module: str
    ) -> list[EditResult]: ...
