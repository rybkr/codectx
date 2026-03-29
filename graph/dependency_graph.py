from __future__ import annotations
import logging
import os
from pathlib import Path
import networkx as nx

from tree_sitter import Language, Parser, Node, Query, QueryCursor
import tree_sitter_python as tspython

log = logging.getLogger("dependency_graph")

EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "dist-packages",
}

PY_LANGUAGE = Language(tspython.language())
parser = Parser()
parser.language = PY_LANGUAGE

FN_QUERY = Query(
    PY_LANGUAGE,
    """
  (function_definition name: (identifier) @fn.name)
""",
)

CALL_QUERY = Query(
    PY_LANGUAGE,
    """
    (call function: (identifier) @call.name)
    (call function: (attribute object: (identifier) @call.obj
         attribute: (identifier) @call.attr))
""",
)

IMPORT_QUERY = Query(
    PY_LANGUAGE,
    """
            (import_statement name: (dotted_name) @import)
(import_from_statement module_name: (dotted_name) @import.from
                              name: (dotted_name) @import.name)
""",
)


def _module_name(path: Path, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            dirname for dirname in dirnames if dirname not in EXCLUDED_DIR_NAMES
        ]
        current_dir = Path(dirpath)
        if any(part in EXCLUDED_DIR_NAMES for part in current_dir.parts):
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = current_dir / filename
            if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
                continue
            files.append(path)
    files.sort()
    return files


def _extract_symbols(source: bytes, module: str) -> dict[str, dict]:
    tree = parser.parse(source)
    symbols = {}
    captures = QueryCursor(FN_QUERY).captures(tree.root_node)
    for n in captures.get("fn.name", []):
        name = n.text.decode()
        qname = f"{module}.{name}"
        fn_node = n.parent
        symbols[qname] = {
            "node": fn_node,
            "kind": "function",
            "interface_hash": _interface_hash(fn_node, source),
        }
    return symbols


def _interface_hash(fn_node: Node, source: bytes) -> int:
    parts = []
    for child in fn_node.children:
        if child.type in ("parameters", "type"):
            parts.append(source[child.start_byte : child.end_byte])
    return hash(b"".join(parts))


def _extract_calls(source: bytes, module: str) -> list[tuple[str, str]]:
    tree = parser.parse(source)
    edges = []
    captures = QueryCursor(CALL_QUERY).captures(tree.root_node)
    for cap_name, nodes in captures.items():
        if cap_name == "call.name":
            for n in nodes:
                caller = _enclosing_function(n, module)
                if caller:
                    edges.append((caller, n.text.decode()))
    return edges


def _enclosing_function(node: Node, module: str) -> str | None:
    current = node.parent
    while current:
        if current.type == "function_definition":
            name = current.child_by_field_name("name").text.decode()
            return f"{module}.{name}"
        current = current.parent
    return None


class DependencyGraph:
    def __init__(self, root: Path):
        self.root: Path = root
        self._g: nx.DiGraph = nx.DiGraph()
        self._symbols: dict[str, dict] = {}

    async def build(self) -> None:
        import asyncio

        await asyncio.to_thread(self._build_sync)

    def _build_sync(self) -> None:
        source_files = _iter_source_files(self.root)
        for path in source_files:
            module = _module_name(path, self.root)
            source = path.read_bytes()
            syms = _extract_symbols(source, module)
            self._symbols.update(syms)
            for qname in syms:
                self._g.add_node(qname)
        for path in source_files:
            module = _module_name(path, self.root)
            source = path.read_bytes()
            for caller, callee in _extract_calls(source, module):
                self._add_edge_if_known(caller, callee)
        log.info(
            "graph built: %d nodes, %d edges",
            self._g.number_of_nodes(),
            self._g.number_of_edges(),
        )

    def _add_edge_if_known(self, caller: str, callee_name: str) -> None:
        candidates = [s for s in self._symbols if s.endswith(f".{callee_name}")]
        for callee in candidates:
            self._g.add_edge(caller, callee)

    def dependents(self, symbol: str) -> set[str]:
        return nx.ancestors(self._g, symbol)

    def interface_hash(self, symbol: str) -> int | None:
        return self._symbols.get(symbol, {}).get("interface_hash")

    def update_file(self, path: Path) -> set[str]:
        module = _module_name(path, self.root)
        source = path.read_bytes()
        new_syms = _extract_symbols(source, module)
        changed = set()
        for qname, data in new_syms.items():
            old = self._symbols.get(qname)
            if old is None or old["interface_hash"] != data["interface_hash"]:
                changed.add(qname)
        self._symbols.update(new_syms)
        return changed
