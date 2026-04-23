from __future__ import annotations

import os
from pathlib import Path
from pathspec import GitIgnoreSpec
from dataclasses import dataclass
from typing import Iterator

from graph.languages import adapter_for_path, LanguageAdapter


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
        path: Path = path if path.is_absolute() else self.root / path

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


def iter_source_files(root: Path) -> Iterator[tuple[Path, LanguageAdapter]]:
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


def is_trackable_source_file(path: Path, root: Path) -> bool:
    try:
        _ = path.relative_to(root)
    except ValueError:
        return False
    return not GitIgnoreMatcher(root).ignores(path, is_dir=False)
