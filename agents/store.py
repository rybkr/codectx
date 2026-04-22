from __future__ import annotations

from datetime import UTC, datetime

from agents.models import (
    AgentSession,
    new_id,
    ObservedSymbol,
    ObservationSource,
    StaleSymbol,
    StaleContextReport,
)
from graph import SymbolGraph, Symbol


class AgentContextStore:
    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._observations: dict[str, dict[str, ObservedSymbol]] = {}

    def register_agent(self, name: str, task: str) -> AgentSession:
        now = datetime.now(UTC)
        session = AgentSession(
            agent_id=new_id(),
            name=name,
            task=task,
            started_at=now,
            last_seen_at=now,
        )
        self._sessions[session.agent_id] = session
        self._observations[session.agent_id] = {}
        return session

    def heartbeat(self, agent_id: str) -> AgentSession | None:
        session = self._sessions.get(agent_id, None)
        if session is None:
            return None

        updated: AgentSession = AgentSession(
            agent_id=session.agent_id,
            name=session.name,
            task=session.task,
            started_at=session.started_at,
            last_seen_at=datetime.now(UTC),
        )
        self._sessions[agent_id] = updated
        return updated

    def record_observation(
        self, agent_id: str, symbols: list[Symbol], source: ObservationSource
    ) -> tuple[ObservedSymbol, ...]:
        observed_symbols: list[ObservedSymbol] = []

        for symbol in symbols:
            observation: ObservedSymbol = ObservedSymbol(
                agent_id=agent_id,
                symbol=symbol.qname,
                interface_hash=symbol.interface_hash,
                body_hash=symbol.body_hash,
                source=source,
                observed_at=datetime.now(UTC),
            )
            self._observations[agent_id][symbol.qname] = observation
            observed_symbols.append(observation)

        return tuple(observed_symbols)

    def affected_agents(self, impacted_symbols: set[str]) -> tuple[AgentSession, ...]:
        return tuple(
            [
                self._sessions[agent_id]
                for agent_id, observations in self._observations.items()
                if any(symbol in impacted_symbols for symbol in observations.keys())
            ]
        )

    def stale_context(self, agent_id: str, graph: SymbolGraph) -> StaleContextReport:
        if agent_id not in self._observations:
            raise KeyError(f"unrecognized agent id: {agent_id}")
        stale_symbols: list[StaleSymbol] = []

        for symbol, observation in self._observations[agent_id].items():
            if not graph.has_symbol(symbol):
                stale_symbols.append(
                    StaleSymbol(
                        symbol=symbol,
                        observed_interface_hash=observation.interface_hash,
                        current_interface_hash=None,
                        observed_body_hash=observation.body_hash,
                        current_body_hash=None,
                        reason=f"{symbol} no longer exists",
                    )
                )
                continue
            symbol_item: Symbol = graph.get_symbol(symbol)
            if not (
                observation.interface_hash == symbol_item.interface_hash
                or (
                    observation.interface_hash is None
                    and symbol_item.interface_hash is None
                )
            ):
                stale_symbols.append(
                    StaleSymbol(
                        symbol=symbol,
                        observed_interface_hash=observation.interface_hash,
                        current_interface_hash=symbol_item.interface_hash,
                        observed_body_hash=observation.body_hash,
                        current_body_hash=symbol_item.body_hash,
                        reason=f"interface for {symbol} has changed",
                    )
                )
            elif not (
                observation.body_hash == symbol_item.body_hash
                or (observation.body_hash is None and symbol_item.body_hash is None)
            ):
                stale_symbols.append(
                    StaleSymbol(
                        symbol=symbol,
                        observed_interface_hash=observation.interface_hash,
                        current_interface_hash=symbol_item.interface_hash,
                        observed_body_hash=observation.body_hash,
                        current_body_hash=symbol_item.body_hash,
                        reason=f"implementation of {symbol} has changed",
                    )
                )

        return StaleContextReport(
            agent_id=agent_id,
            stale_symbols=tuple(stale_symbols),
        )

    def release_agent(self, agent_id: str) -> None:
        self._sessions.pop(agent_id, None)
        self._observations.pop(agent_id, None)
