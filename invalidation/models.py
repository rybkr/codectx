from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactReport:
    changed_symbols: tuple[str, ...]
    impacted_symbols: tuple[str, ...]

    @property
    def payload(self) -> dict[str, object]:
        return {
            "changed_symbols": self.changed_symbols,
            "impacted_symbols": self.impacted_symbols,
        }
