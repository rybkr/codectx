from __future__ import annotations
import logging
from pathlib import Path
from graph.dependency_graph import DependencyGraph
from graph.dependency_graph import EXCLUDED_DIR_NAMES, _iter_source_files
from graph.semantic_diff import classify_edits, EditKind, EditResult

log = logging.getLogger("incremental_update")

_file_cache: dict[Path, bytes] = {}


def apply_commit(
    changed_files: list[Path],
    graph: DependencyGraph,
) -> list[EditResult]:
    contract_edits: list[EditResult] = []

    for path in changed_files:
        if not path.suffix == ".py":
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue

        new_source = path.read_bytes()
        old_source = _file_cache.get(path, b"")
        _file_cache[path] = new_source

        try:
            module = ".".join(path.relative_to(graph.root).with_suffix("").parts)
        except ValueError:
            log.warning("skipping file outside graph root: %s", path)
            continue

        edits = classify_edits(old_source, new_source, module)
        for edit in edits:
            if edit.kind == EditKind.CONTRACT:
                contract_edits.append(edit)
                log.info("contract edit: %s", edit.symbol)
            elif edit.kind == EditKind.REMOVED:
                contract_edits.append(edit)
                log.info("symbol removed: %s", edit.symbol)

        graph.update_file(path)

    return contract_edits


def prime_cache(root: Path) -> None:
    for path in _iter_source_files(root):
        _file_cache[path] = path.read_bytes()
