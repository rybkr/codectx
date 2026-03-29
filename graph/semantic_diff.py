from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from tree_sitter import Language, Parser, Node
import tree_sitter_python as tspython

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)


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
    q = PY_LANGUAGE.query("(function_definition name: (identifier) @name)")
    result = {}
    for _, nodes in q.captures(tree.root_node).items():
        for n in nodes:
            result[n.text.decode()] = n.parent
    return result


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
