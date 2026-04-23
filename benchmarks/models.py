from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkAgent:
    name: str
    task: str
    observes: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkExpected:
    changed_symbols: tuple[str, ...]
    impacted_symbols: tuple[str, ...]
    affected_agents: tuple[str, ...]
    stale_symbols: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    root: Path
    agents: tuple[BenchmarkAgent, ...]
    update_files: tuple[str, ...]
    expected: BenchmarkExpected


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    passed: bool
    changed_symbols: tuple[str, ...]
    impacted_symbols: tuple[str, ...]
    affected_agents: tuple[str, ...]
    stale_symbols: tuple[str, ...]
