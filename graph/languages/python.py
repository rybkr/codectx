from __future__ import annotations

import hashlib
from pathlib import Path
from tree_sitter import Language, Parser, Node, Query, QueryCursor
import tree_sitter_python

from graph.models import (
    Symbol,
    SymbolRef,
    SymbolKind,
    RefKind,
    ParsedFile,
    ImportBinding,
)
from graph.languages.base import LanguageAdapter


_FUNCTION_QUERY: str = (
    f"(function_definition name: (identifier) @{SymbolKind.FUNCTION}.name)"
)
_CLASS_QUERY: str = f"(class_definition name: (identifier) @{SymbolKind.CLASS}.name)"
_VARIABLE_QUERY: str = f"""
    (assignment left: (identifier) @{SymbolKind.VARIABLE}.name)
    (assignment left: (pattern_list (identifier) @{SymbolKind.VARIABLE}.name))
    (assignment left: (list_pattern (identifier) @{SymbolKind.VARIABLE}.name))
    (augmented_assignment left: (identifier) @{SymbolKind.VARIABLE}.name)
"""
_CALLS_QUERY: str = f"""
      (call function: (identifier) @{RefKind.CALLS}.name)
      (call function: (attribute
          object: (_) @{RefKind.CALLS}.obj
          attribute: (identifier) @{RefKind.CALLS}.attr))
  """
_IMPORTS_QUERY: str = f"""
    (import_statement name: (dotted_name) @{RefKind.IMPORTS})
    (import_from_statement module_name: (dotted_name) @{RefKind.IMPORTS}.from name: (dotted_name) @{RefKind.IMPORTS}.name)
"""
_REFERENCES_TYPE_QUERY: str = f"""
    (typed_parameter type: (type (identifier)) @{RefKind.REFERENCES_TYPE}.ref)
    (typed_parameter type: (type (attribute)) @{RefKind.REFERENCES_TYPE}.ref)
    (function_definition return_type: (type) @{RefKind.REFERENCES_TYPE}.ref)
    (class_definition superclasses: (argument_list (identifier) @{RefKind.REFERENCES_TYPE}.ref))
    (class_definition superclasses: (argument_list (attribute) @{RefKind.REFERENCES_TYPE}.ref))
"""


class PythonAdapter(LanguageAdapter):
    name: str = "python"

    _language = Language(tree_sitter_python.language())
    _parser = Parser(language=_language)
    _queries: dict[SymbolKind | RefKind, Query] = {
        SymbolKind.FUNCTION: Query(_language, _FUNCTION_QUERY),
        SymbolKind.CLASS: Query(_language, _CLASS_QUERY),
        SymbolKind.VARIABLE: Query(_language, _VARIABLE_QUERY),
        RefKind.CALLS: Query(_language, _CALLS_QUERY),
        RefKind.IMPORTS: Query(_language, _IMPORTS_QUERY),
        RefKind.REFERENCES_TYPE: Query(_language, _REFERENCES_TYPE_QUERY),
    }

    def supports_path(self, path: Path) -> bool:
        return path.suffix == ".py"

    def module_name(self, path: Path, root: Path) -> str:
        return ".".join(path.relative_to(root).with_suffix("").parts)

    def parse_file(self, path: Path, source: bytes, root: Path) -> ParsedFile:
        module: str = self.module_name(path, root)
        rel_path: Path = path.relative_to(root).as_posix()
        root: Node = self._parser.parse(source).root_node
        return ParsedFile(
            module=module,
            symbols=self._extract_symbols(root, module, rel_path, source),
            refs=self._extract_refs(root, module),
            imports=self._extract_imports(root),
        )

    # def classify_edits(
    #     self, old_src: bytes, new_src: bytes, module: str
    # ) -> list[EditResult]: ...

    def _extract_symbols(
        self, root: Node, module: str, rel_path: Path, source: bytes
    ) -> list[Symbol]:
        symbols: list[Symbol] = []

        for symbol_kind in [SymbolKind.CLASS, SymbolKind.FUNCTION, SymbolKind.VARIABLE]:
            captures = QueryCursor(self._queries[symbol_kind]).captures(root)
            for n in captures.get(f"{symbol_kind}.name", []):
                symbols.append(
                    Symbol(
                        qname=self._qualified_symbol_name(n.parent, module),
                        kind=symbol_kind,
                        interface_hash=self._interface_hash(
                            symbol_kind, n.parent, source
                        ),
                        path=rel_path,
                        module=module,
                        parent=self._parent_symbol_name(n.parent, module),
                    )
                )

        return [
            Symbol(
                qname=module,
                kind=SymbolKind.MODULE,
                path=rel_path,
                module=module,
                parent=None,
            ),
            *symbols,
        ]

    def _extract_refs(self, root: Node, module: str) -> list[SymbolRef]:
        refs: list[SymbolRef] = []
        refs.extend(self._extract_call_refs(root, module))
        refs.extend(self._extract_type_refs(root, module))
        return refs

    def _extract_call_refs(self, root: Node, module: str) -> list[SymbolRef]:
        refs: list[SymbolRef] = []

        call_matches = QueryCursor(self._queries[RefKind.CALLS]).matches(root)
        for _, captures in call_matches:
            for node in captures.get(f"{RefKind.CALLS}.name", []):
                src_symbol: str = self._qualified_symbol_name(node, module)
                if src_symbol is not None:
                    refs.append(
                        SymbolRef(
                            source_symbol=src_symbol,
                            target_name=node.text.decode(),
                            kind=RefKind.CALLS,
                            module=module,
                        )
                    )

            recv_nodes = captures.get(f"{RefKind.CALLS}.obj", [])
            attr_nodes = captures.get(f"{RefKind.CALLS}.attr", [])

            recv_name = recv_nodes[0].text.decode() if recv_nodes else None
            for node in attr_nodes:
                src_symbol = self._qualified_symbol_name(node, module)
                if src_symbol is not None:
                    refs.append(
                        SymbolRef(
                            source_symbol=src_symbol,
                            target_name=node.text.decode(),
                            kind=RefKind.CALLS,
                            module=module,
                            recv_name=recv_name,
                        )
                    )

        return refs

    def _extract_type_refs(self, root: Node, module: str) -> list[SymbolRef]:
        refs: list[SymbolRef] = []

        captures = QueryCursor(self._queries[RefKind.REFERENCES_TYPE]).captures(root)
        for _name, nodes in captures.items():
            for node in nodes:
                src_symbol = self._qualified_symbol_name(node, module)
                if src_symbol is not None:
                    refs.append(
                        SymbolRef(
                            source_symbol=src_symbol,
                            target_name=node.text.decode(),
                            kind=RefKind.REFERENCES_TYPE,
                            module=module,
                        )
                    )
        return refs

    def _extract_imports(self, root: Node) -> list[ImportBinding]:
        imports: list[ImportBinding] = []

        def import_alias_parts(node: Node) -> tuple[str, str]:
            if node.type == "aliased_import":
                name_node: Node = node.child_by_field_name("name")
                alias_node: Node = node.child_by_field_name("alias")
                if name_node is None:
                    return "", ""
                target = name_node.text.decode()
                local = alias_node.text.decode() if alias_node else target
                return target, local
            return node.text.decode(), node.text.decode()

        def is_same_node(a: Node, b: Node) -> bool:
            return (
                a.type == b.type
                and a.start_byte == b.start_byte
                and a.end_byte == b.end_byte
            )

        def walk(node: Node) -> None:
            nonlocal imports

            if node.type == "import_statement":
                for child in node.named_children:
                    if child.type not in {"dotted_name", "aliased_import"}:
                        continue

                    target_module, local_name = import_alias_parts(child)
                    if target_module:
                        imports.append(
                            ImportBinding(
                                local_name=local_name,
                                target_qname=None,
                                target_module=target_module,
                            )
                        )

            elif node.type == "import_from_statement":
                module_node = node.child_by_field_name("module_name")
                if module_node is None:
                    return

                module_name: str = module_node.text.decode()
                for child in node.named_children:
                    if is_same_node(child, module_node) or child.type not in {
                        "dotted_name",
                        "aliased_import",
                    }:
                        continue

                    imported_name, local_name = import_alias_parts(child)
                    if not imported_name:
                        continue

                    target_qname: str = f"{module_name}.{imported_name}"
                    imports.append(
                        ImportBinding(
                            local_name=local_name,
                            target_qname=target_qname,
                            target_module=module_name,
                        )
                    )

            for child in node.named_children:
                walk(child)

        walk(root)
        return imports

    def _qualified_symbol_name(self, node: Node, module: str) -> str:
        parts: list[str] = []

        if node.type in {"assignment"}:
            identifier: Node = next(
                (child for child in node.children if child.type == "identifier"), None
            )
            if identifier is not None:
                parts.append(identifier.text.decode())

        current: Node | None = node
        while current:
            if current.type in {"function_definition", "class_definition"}:
                name_node = current.child_by_field_name("name")
                if name_node is not None:
                    parts.append(name_node.text.decode())
            current = current.parent

        parts.reverse()
        return ".".join([module, *parts])

    def _parent_symbol_name(self, node: Node, module: str) -> str | None:
        current: Node | None = node.parent
        while current is not None:
            if current.type in {"function_definition", "class_definition"}:
                return self._qualified_symbol_name(current, module)
            current = current.parent
        return None

    def _interface_hash(
        self, symbol_kind: SymbolKind, node: Node, source: bytes
    ) -> int:
        parts: list[bytes] = []

        if symbol_kind == SymbolKind.FUNCTION:
            name = node.child_by_field_name("name")
            type_params = node.child_by_field_name("type_parameters")
            params = node.child_by_field_name("parameters")
            ret = node.child_by_field_name("return_type")
            for n in (name, type_params, params, ret):
                if n is not None:
                    parts.append(self._normalize(n, source))

        elif symbol_kind == SymbolKind.CLASS:
            name = node.child_by_field_name("name")
            type_params = node.child_by_field_name("type_parameters")
            superclasses = node.child_by_field_name("superclasses")
            for n in (name, type_params, superclasses):
                if n is not None:
                    parts.append(self._normalize(n, source))

        elif symbol_kind == SymbolKind.VARIABLE:
            type_node = node.child_by_field_name("type")
            name = node.child_by_field_name("left") or node.child_by_field_name("name")
            for n in (name, type_node):
                if n is not None:
                    parts.append(self._normalize(n, source))

        if not parts:
            return 0
        digest = hashlib.blake2b(b"\x00".join(parts), digest_size=8).digest()
        return int.from_bytes(digest, "big")

    def _normalize(self, node: Node, source: bytes) -> bytes:
        text: bytes = source[node.start_byte : node.end_byte]
        return b" ".join(text.split())
