from __future__ import annotations

import os
from pathlib import Path
from pathspec import GitIgnoreSpec
import networkx as nx
from dataclasses import dataclass

from core.models import SymbolKind
from graph.languages import adapter_for_path
from graph.languages.base import ParsedFile


EXCLUDED_DIR_NAMES: set[str] = {".git"}


@dataclass(frozen=True)
class IgnoreLayer:
    root: Path
    spec: GitIgnoreSpec


class GitIgnoreMatcher:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._cache: dict[Path, tuple[IgnoreLayer, ...]] = {}

    def ignores(self, path: Path, *, is_dir: bool) -> bool:
        path: Path = path if path.is_absolute else self.root / path

        try:
            path.relative_to(self.root)
        except ValueError:
            return True

        matched: bool = False
        for layer in self._layers_for_dir(path.parent):
            try:
                relative = path.relative_to(layer.root).as_posix()
            except ValueError:
                continue
            if is_dir:
                relative = relative.rstrip("/") + "/"
            if layer.spec.match_file(relative):
                matched = True

        return matched

    def _layers_for_dir(self, directory: Path) -> tuple[IgnoreLayer, ...]:
        directory: Path = directory.resolve()
        if directory in self._cache:
            return self._cache[directory]

        if directory == self.root:
            layers: tuple[IgnoreLayer, ...] = ()
        else:
            layers = self._layers_for_dir(directory.parent)

        gitignore_path: Path = directory / ".gitignore"
        if gitignore_path.is_file():
            lines = gitignore_path.read_text(encoding="utf-8").splitlines()
            layers = (
                *layers,
                IgnoreLayer(root=directory, spec=GitIgnoreSpec.from_lines(lines)),
            )

        self._cache[directory] = layers
        return layers


def build_graph_from_disk(root: Path) -> tuple[nx.DiGraph, dict[str, SymbolDef]]:
    return build_graph_from_sources(
        root, {path: path.read_bytes() for path, _ in iter_trackable_files(root)}
    )


def build_graph_from_sources(
    root: Path, sources: dict[Path, bytes]
) -> tuple[nx.DiGraph, dict[str, SymbolDef]]:
    root: Path = root.resolve()
    graph = nx.DiGraph()
    symbols: dict[str, SymbolDef] = {}
    parsed_files: list[ParsedFile] = []

    for path in sources.keys():
        adapter: LanguageAdapter = adapter_for_path(path)
        if adapter is None:
            continue

        parsed_file: ParsedFile = adapter.parse_file(path, sources[path], root)
        parsed_files.append(parsed_file)
        for symbol in parsed_file.symbols:
            symbols[symbol.qname] = symbol
            graph.add_node(symbol.qname)

    for parsed_file in parsed_files:
        for ref in parsed_file.refs:
            for target in _resolve_ref(ref, symbols):
                graph.add_edge(ref.source_symbol, target)

    return graph, symbols


def iter_trackable_files(root: Path) -> Iterator[tuple[Path, LanguageAdapter]]:
    root: Path = root.resolve()
    ignore_matcher = GitIgnoreMatcher(root)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            if dirname in EXCLUDED_DIR_NAMES:
                continue

            child: Path = current_dir / dirname
            if ignore_matcher.ignores(child, is_dir=True):
                continue

            kept_dirs.append(dirname)

        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            path: Path = current_dir / filename
            if ignore_matcher.ignores(path, is_dir=False):
                continue

            adapter: LanguageAdapter = adapter_for_path(path)
            if adapter is None:
                continue

            yield path, adapter


def _resolve_ref(ref: SymbolRef, symbols: dict[str, SymbolDef]) -> list[str]:
    targets: list[str] = [
        symbol for symbol in symbols.keys() if symbol.endswith(f".{ref.target_name}")
    ]

    expanded: list[str] = []
    for symbol in targets:
        expanded.append(symbol)
        if symbols[symbol].kind == SymbolKind.CLASS:
            init_symbol = f"{symbol}.__init__"
            if init_symbol in symbols:
                expanded.append(init_symbol)

    return expanded
