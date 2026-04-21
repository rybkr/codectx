from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
#from graph.dependency_graph import DependencyGraph
from graph.semantic_diff import classify_edits, EditKind, EditResult

log = logging.getLogger("incremental_update")

_file_cache: dict[Path, bytes] = {}


@dataclass(frozen=True)
class FileUpdate:
    path: Path
    old_source: bytes
    new_source: bytes


def classify_file_update(update: FileUpdate, root: Path) -> list[EditResult]:
    module = ".".join(update.path.relative_to(root).with_suffix("").parts)
    return classify_edits(update.old_source, update.new_source, module)


def actionable_edits(edits: list[EditResult]) -> list[EditResult]:
    return [
        edit for edit in edits if edit.kind in {EditKind.CONTRACT, EditKind.REMOVED}
    ]


def apply_file_updates(
    updates: list[FileUpdate],
    graph: DependencyGraph,
) -> list[EditResult]:
    all_edits: list[EditResult] = []
    overrides: dict[Path, bytes] = {}
    for update in updates:
        if update.path.suffix != ".py":
            continue
        try:
            update.path.relative_to(graph.root)
        except ValueError:
            log.warning("skipping file outside graph root: %s", update.path)
            continue
        all_edits.extend(classify_file_update(update, graph.root))
        overrides[update.path] = update.new_source
    if overrides:
        graph.rebuild_with_overrides(overrides)
    return all_edits


def apply_commit(
    changed_files: list[Path],
    graph: DependencyGraph,
) -> list[EditResult]:
    contract_edits: list[EditResult] = []
    updates: list[FileUpdate] = []

    for path in changed_files:
        if not path.suffix == ".py":
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue

        new_source = path.read_bytes()
        old_source = _file_cache.get(path, b"")
        _file_cache[path] = new_source

        updates.append(
            FileUpdate(path=path, old_source=old_source, new_source=new_source)
        )

    edits = apply_file_updates(updates, graph)
    for edit in actionable_edits(edits):
        contract_edits.append(edit)
        if edit.kind == EditKind.CONTRACT:
            log.info("contract edit: %s", edit.symbol)
        elif edit.kind == EditKind.REMOVED:
            log.info("symbol removed: %s", edit.symbol)

    return contract_edits


def prime_cache(root: Path) -> None:
    for path in _iter_source_files(root):
        _file_cache[path] = path.read_bytes()
