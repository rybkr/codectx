from __future__ import annotations

from dataclasses import dataclass

from graph.models import ResolvedRef


@dataclass(frozen=True)
class ImpactReport:
    changed_symbols: tuple[str, ...]
    impacted_symbols: tuple[str, ...]
