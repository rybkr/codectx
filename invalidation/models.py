from __future__ import annotations

from dataclasses import dataclass

from agents.models import AgentSession


@dataclass(frozen=True)
class ImpactReport:
    changed_symbols: tuple[str, ...]
    impacted_symbols: tuple[str, ...]
    affected_agents: tuple[AgentSession, ...] = ()

    @property
    def payload(self) -> dict[str, object]:
        return {
            "changed_symbols": self.changed_symbols,
            "impacted_symbols": self.impacted_symbols,
            "affected_agents": [agent.payload for agent in self.affected_agents],
        }
