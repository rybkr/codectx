from pathlib import Path

from graph.languages.base import LanguageAdapter
from graph.languages.python import PythonAdapter

ADAPTERS: list[LanguageAdapter] = [PythonAdapter()]


def adapter_for_path(path: Path) -> LanguageAdapter | None:
    valid_adapters = [adapter for adapter in ADAPTERS if adapter.supports_path(path)]
    return valid_adapters[0] if len(valid_adapters) >= 1 else None
