from __future__ import annotations

from pathlib import Path
from tree_sitter import Language, Parser, Node, Query, QueryCursor
import tree_sitter_python

from core.models import SymbolKind, RefKind
from graph.languages.base import SymbolDef, SymbolRef, ParsedFile, LanguageAdapter


class PythonAdapter(LanguageAdapter):
    name: str = "python"

    _language = Language(tree_sitter_python.language())
    _parser = Parser(language=_language)

    _queries: dict[str, Query] = {
        "function": Query(
            _language, "(function_definition name: (identifier) @function.name)"
        ),
        "class": Query(_language, "(class_definition name: (identifier) @class.name)"),
        "call": Query(
            _language,
            "(call function: (identifier) @call.name) (call function: (attribute object: (identifier) @call.obj attribute: (identifier) @call.attr))",
        ),
        "import": Query(
            _language,
            "(import_statement name: (dotted_name) @import) (import_from_statement module_name: (dotted_name) @import.from name: (dotted_name) @import.name)",
        ),
    }

    def supports_path(self, path: Path) -> bool:
        return path.suffix == ".py"

    def module_name(self, path: Path, root: Path) -> str:
        return ".".join(path.relative_to(root).with_suffix("").parts)

    def parse_file(self, path: Path, source: bytes, root: Path) -> ParsedFile:
        module: str = self.module_name(path, root)
        root_node: Node = self._parser.parse(source).root_node
        symbols: list[SymbolDef] = self._extract_symbols(root_node, source, module)
        refs: list[SymbolRef] = self._extract_refs(root_node, module)
        return ParsedFile(module=module, symbols=symbols, refs=refs)

    def classify_edits(
        self, old_src: bytes, new_src: bytes, module: str
    ) -> list[EditResult]: ...

    def _extract_symbols(
        self, root: Node, source: bytes, module: str
    ) -> list[SymbolDef]:
        symbols: list[SymbolDef] = []

        for symbol_kind in [SymbolKind.CLASS, SymbolKind.FUNCTION]:
            captures = QueryCursor(self._queries[symbol_kind]).captures(root)
            for n in captures.get(f"{symbol_kind}.name", []):
                node: Node = n.parent
                qname: str = self._qualified_symbol_name(node, module)
                symbols.append(
                    SymbolDef(
                        qname=qname,
                        kind=symbol_kind,
                        interface_hash=self._interface_hash(symbol_kind, node, source),
                    )
                )

        return symbols

    def _extract_refs(self, root: Node, module: str) -> list[SymbolRef]:
        refs: list[SymbolRef] = []

        for ref_kind in [RefKind.CALL]:
            captures = QueryCursor(self._queries[ref_kind]).captures(root)
            for name, nodes in captures.items():
                if name not in {f"{ref_kind}.name", f"{ref_kind}.attr"}:
                    continue
                for node in nodes:
                    src_symbol = self._qualified_symbol_name(node, module)
                    if src_symbol is not None:
                        refs.append(
                            SymbolRef(
                                source_symbol=src_symbol,
                                target_name=node.text.decode(),
                                kind=RefKind.CALL,
                            )
                        )

        return refs

    def _qualified_symbol_name(self, node: Node, module: str) -> str:
        parts: list[str] = []
        current: Node | None = node

        while current:
            if current.type in {"function_definition", "class_definition"}:
                name_node = current.child_by_field_name("name")
                if name_node is not None:
                    parts.append(name_node.text.decode())
            current = current.parent

        parts.reverse()
        return ".".join([module, *parts])

    def _interface_hash(
        self, symbol_kind: SymbolKind, node: Node, source: bytes
    ) -> int:
        parts: list[str] = []

        interface_components: set[str] = set()
        if symbol_kind == SymbolKind.FUNCTION:
            interface_components |= {"parameters", "type"}
        elif symbol_kind == SymbolKind.CLASS:
            interface_components |= {"argument_list", "type_parameter"}

        for child in node.children:
            if child.type in interface_components:
                parts.append(source[child.start_byte : child.end_byte])

        return hash(b"".join(parts))
