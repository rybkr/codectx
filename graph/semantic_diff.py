from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto

from tree_sitter import Language, Parser, Node, Query, QueryCursor
import tree_sitter_python as tspython

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

FN_QUERY = Query(
    PY_LANGUAGE,
    """
  (function_definition name: (identifier) @fn.name)
""",
)


class EditKind(Enum):
    CONTRACT = auto()
    INTERNAL = auto()
    ADDED = auto()
    REMOVED = auto()


@dataclass
class EditResult:
    symbol: str
    kind: EditKind
    old_interface: bytes | None = None
    new_interface: bytes | None = None


def _get_interface(fn_node: Node, source: bytes) -> bytes:
    parts = []
    for child in fn_node.children:
        if child.type == "parameters":
            parts.append(source[child.start_byte : child.end_byte])
        elif child.type == "type":
            parts.append(source[child.start_byte : child.end_byte])
    return b" | ".join(parts)


def _fn_nodes_by_name(source: bytes) -> dict[str, Node]:
    tree = parser.parse(source)
    result: dict[str, Node] = {}
    captures = QueryCursor(FN_QUERY).captures(tree.root_node)
    for node in captures.get("fn.name", []):
        fn_node = node.parent
        result[_qualified_symbol_name(fn_node)] = fn_node
    return result


def _qualified_symbol_name(node: Node) -> str:
    parts: list[str] = []
    current: Node | None = node
    while current:
        if current.type in {"function_definition", "class_definition"}:
            name_node = current.child_by_field_name("name")
            if name_node is not None:
                parts.append(name_node.text.decode())
        current = current.parent
    parts.reverse()
    return ".".join(parts)


def classify_edits(
    old_source: bytes,
    new_source: bytes,
    module: str,
) -> list[EditResult]:
    old_fns = _fn_nodes_by_name(old_source)
    new_fns = _fn_nodes_by_name(new_source)
    results = []

    for name, new_node in new_fns.items():
        qname = f"{module}.{name}"
        if name not in old_fns:
            results.append(EditResult(qname, EditKind.ADDED))
            continue
        old_iface = _get_interface(old_fns[name], old_source)
        new_iface = _get_interface(new_node, new_source)
        if old_iface != new_iface:
            results.append(EditResult(qname, EditKind.CONTRACT, old_iface, new_iface))
        else:
            old_body = old_source[old_fns[name].start_byte : old_fns[name].end_byte]
            new_body = new_source[new_node.start_byte : new_node.end_byte]
            if old_body != new_body:
                results.append(EditResult(qname, EditKind.INTERNAL))

    for name in old_fns:
        if name not in new_fns:
            results.append(EditResult(f"{module}.{name}", EditKind.REMOVED))
    return results
