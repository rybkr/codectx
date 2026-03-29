from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from detection.context_manager import ContextManager
from graph.dependency_graph import DependencyGraph
from graph.incremental_update import apply_commit
from graph.semantic_diff import EditResult

log = logging.getLogger("invalidation_engine")


class InvalidationEngine:
    def __init__(self, graph: DependencyGraph, context_manager: ContextManager):
        self.graph = graph
        self.context_manager = context_manager

    async def invalidate_symbols(self, symbols: Iterable[str]) -> dict[int, set[str]]:
        impacted_by_agent: dict[int, set[str]] = {}

        for symbol in symbols:
            affected = {symbol, *self.graph.dependents(symbol)}
            for affected_symbol in affected:
                for agent in self.context_manager.stale_agents_for_symbol(
                    affected_symbol
                ):
                    impacted_by_agent.setdefault(agent.id, set()).add(affected_symbol)
                    await agent.receive_invalidation(
                        affected_symbol,
                        "symbol_stale",
                        {
                            "source_symbol": symbol,
                            "invalidated_symbol": affected_symbol,
                        },
                    )
        return impacted_by_agent

    async def invalidate_edits(
        self,
        edits: Iterable[EditResult],
    ) -> dict[int, set[str]]:
        return await self.invalidate_symbols(edit.symbol for edit in edits)

    async def apply_commit(self, changed_files: list[Path]) -> dict[int, set[str]]:
        edits = apply_commit(changed_files, self.graph)
        if not edits:
            return {}

        impacted = await self.invalidate_edits(edits)
        for agent_id, symbols in sorted(impacted.items()):
            log.info("agent %s invalidated: %s", agent_id, sorted(symbols))
        return impacted
