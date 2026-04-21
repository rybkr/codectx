from dataclasses import dataclass
from enum import StrEnum, auto


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


@dataclass(frozen=True)
class Symbol:
    qname: str
    kind: SymbolKind
    interface_hash: int | None = None
    path: str | None = None
    module: str | None = None
    parent: str | None = None


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
