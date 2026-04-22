from __future__ import annotations

from pathlib import Path
from typing import Protocol

from graph.models import ParsedFile, EditResult


class LanguageAdapter(Protocol):
    name: str

    def supports_path(self, path: Path) -> bool: ...

    def module_name(self, path: Path, root: Path) -> str: ...

    def parse_file(self, Path: Path, source: bytes, root: Path) -> ParsedFile: ...

    def classify_edits(
        self, old_src: bytes, new_src: bytes, module: str
    ) -> list[EditResult]: ...
