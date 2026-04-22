from __future__ import annotations

from graph import SymbolGraph
from graph.models import RefKind
from invalidation.models import ImpactReport


class InvalidationEngine:
    def __init__(self, graph: SymbolGraph):
        self._graph = graph

    def impacted_symbols(self, changed_symbols: set[str]) -> ImpactReport:
        impacted_symbols: set[str] = set()

        for symbol in changed_symbols:
            if not self._graph.has_symbol(symbol):
                continue
            for ref_kind in [RefKind.CALLS, RefKind.IMPORTS, RefKind.REFERENCES_TYPE]:
                impacted_symbols.update(
                    set(self._graph.ancestors(symbol, kind=ref_kind))
                )

        return ImpactReport(
            changed_symbols=tuple(sorted(changed_symbols)),
            impacted_symbols=tuple(sorted(impacted_symbols)),
        )
