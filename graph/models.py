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

    @property
    def payload(self) -> dict[str, object]:
        return {
            "start_line": self.start_line,
            "start_col": self.start_col,
            "start_byte": self.start_byte,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "end_byte": self.end_byte,
        }


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

    @property
    def payload(self) -> dict[str, object]:
        result = {
            "qname": self.qname,
            "name": self.name,
            "kind": self.kind.value,
            "path": str(self.path),
            "module": self.module,
            "language": self.language,
            "interface_hash": self.interface_hash,
        }
        if self.parent_qname is not None:
            result["parent_qname"] = self.parent_qname
        if self.span is not None:
            result["span"] = self.span.payload
        if self.name_span is not None:
            result["name_span"] = self.name_span.payload
        if self.body_hash is not None:
            result["body_hash"] = self.body_hash
        return result

    @property
    def body(self) -> str | None:
        if self.span is None:
            return None
        return self.path.read_bytes()[self.span.start_byte : self.span.end_byte].decode(
            "utf-8"
        )

    @property
    def summary(self) -> str:
        if self.body is None:
            return self.qname
        return f"{self.qname}: {'\n'.join(self.body.splitlines()[:6])}"


@dataclass(frozen=True)
class SymbolDetails:
    record: Symbol
    dependencies: tuple[Symbol, ...]
    dependents: tuple[Symbol, ...]

    @property
    def payload(self) -> dict[str, object]:
        return {
            "record": self.record.payload,
            "dependencies": [d.payload for d in self.dependencies],
            "dependents": [d.payload for d in self.dependents],
        }


@dataclass(frozen=True)
class SymbolRef:
    source_symbol: str
    target_name: str
    kind: RefKind
    module: str
    recv_name: str | None = None


@dataclass(frozen=True)
class ResolvedRef:
    source_symbol: str
    target_symbol: str
    target_name: str
    kind: RefKind
    module: str
    recv_name: str | None = None


@dataclass(frozen=True)
class UnresolvedRef:
    ref: SymbolRef
    reason: str


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


@dataclass(frozen=True)
class BuildReport:
    root: Path
    symbols: int
    unresolved_refs: int

    @property
    def payload(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "symbols": self.symbols,
            "unresolved_refs": self.unresolved_refs,
        }
