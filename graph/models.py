from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path


class SymbolKind(StrEnum):
    CLASS = auto()
    VARIABLE = auto()
    FUNCTION = auto()
    MODULE = auto()


class RefKind(StrEnum):
    CONTAINS = auto()
    CALLS = auto()
    IMPORTS = auto()
    REFERENCES_TYPE = auto()


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start_line: int
    start_col: int
    start_byte: int
    end_line: int
    end_col: int
    end_byte: int


@dataclass(frozen=True, slots=True)
class Symbol:
    qname: str
    name: str
    kind: SymbolKind
    path: Path
    module: str
    language: str
    parent_qname: str | None = None
    span: SourceSpan | None = None
    name_span: SourceSpan | None = None
    interface_hash: int | None = None
    body_hash: int | None = None


@dataclass(frozen=True)
class SymbolRef:
    source_symbol: str
    target_name: str
    kind: RefKind
    module: str
    recv_name: str | None = None


type SymbolTable = dict[str, Symbol]


@dataclass(frozen=True)
class ImportBinding:
    local_name: str
    target_qname: str | None
    target_module: str | None


@dataclass(frozen=True)
class ParsedFile:
    module: str
    symbols: list[Symbol]
    refs: list[SymbolRef]
    imports: list[ImportBinding]

    @property
    def symbol_table(self) -> SymbolTable:
        return {symbol.qname: symbol for symbol in self.symbols}


class EditKind(StrEnum):
    ADDED = auto()
    DELETED = auto()
    CONTRACT = auto()
    INTERNAL = auto()


@dataclass(frozen=True)
class EditResult:
    symbol: str
    kind: EditKind
    old_interface: bytes | None = None
    new_interface: bytes | None = None
