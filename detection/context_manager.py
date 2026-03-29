from __future__ import annotations

from collections.abc import Iterable

from agents.base_agent import BaseAgent


class ContextManager:
    def __init__(self, agents: Iterable[BaseAgent]):
        self.agents = list(agents)

    def agents_for_symbol(self, symbol: str) -> list[BaseAgent]:
        return [agent for agent in self.agents if agent.beliefs.has_symbol(symbol)]

    def stale_agents_for_symbol(self, symbol: str) -> list[BaseAgent]:
        impacted: list[BaseAgent] = []
        for agent in self.agents_for_symbol(symbol):
            agent.beliefs.mark_stale(symbol)
            impacted.append(agent)
        return impacted

    def stale_symbols_for_agent(self, agent: BaseAgent) -> list[str]:
        return agent.beliefs.stale_symbols()
