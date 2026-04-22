from __future__ import annotations

from datetime import UTC, datetime, timedelta

from coordination.models import AgentSession, Claim, ClaimMode, Observation, new_id


class CoordinationStore:
    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._claims: dict[str, Claim] = {}
        self._observations: list[Observation] = []

    def register_agent(self, name: str, task: str) -> AgentSession:
        now = datetime.now(UTC)
        session = AgentSession(
            id=new_id(),
            name=name,
            task=task,
            started_at=now,
            last_seen_at=now,
        )
        self._sessions[session.id] = session
        return session

    def heartbeat(self, agent_id: str) -> AgentSession | None:
        session = self._sessions.get(agent_id, None)
        if session is None:
            return None

        updated: AgentSession = AgentSession(
            id=session.id,
            name=session.name,
            task=session.task,
            started_at=session.started_at,
            last_seen_at=datetime.now(UTC),
        )
        self._sessions[agent_id] = updated
        return updated

    def add_observation(
        self, agent_id: str, symbols: list[str], source: str
    ) -> Observation:
        observation: Observation = Observation(
            agent_id=agent_id,
            symbols=tuple(symbols),
            source=source,
        )
        self._observations.append(observation)
        return observation

    def claim(
        self,
        agent_id: str,
        *,
        symbols: list[str] | None = None,
        paths: list[str] | None = None,
        mode: ClaimMode = ClaimMode.WRITE,
        ttl_seconds: int = 300,
    ) -> Claim:
        now = datetime.now(UTC)
        claim = Claim(
            id=new_id(),
            agent_id=agent_id,
            symbols=tuple(symbols or []),
            paths=tuple(paths or []),
            mode=mode,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self._claims[claim.id] = claim
        return claim

    def active_claims(self) -> list[Claim]:
        now = datetime.now(UTC)
        return [claim for claim in self._claims.values() if claim.expires_at > now]

    def release_claims(self, agent_id: str) -> int:
        claim_ids: list[str] = [
            ID for ID, claim in self._claims.items() if claim.agent_id == agent_id
        ]
        for claim_id in claim_ids:
            del self._claims[claim_id]
        return len(claim_ids)

    def conflicting_claims(
        self,
        *,
        agent_id: str,
        symbols: list[str] | None = None,
        paths: list[str] | None = None,
    ) -> list[Claim]:
        wanted_symbols: set[str] = set(symbols or [])
        wanted_paths: set[str] = set(paths or [])
        conflicts: list[Claim] = []

        for claim in self.active_claims():
            if claim.agent_id == agent_id:
                continue
            elif (
                len(wanted_symbols.intersection(claim.symbols)) > 0
                or len(wanted_paths.intersection(claim.paths)) > 0
            ):
                conflicts.append(claim)

        return conflicts
