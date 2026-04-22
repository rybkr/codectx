from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from uuid import uuid4


class ObservationSource(StrEnum):
    RELEVANT_SYMBOLS = auto()
    SYMBOL_DETAILS = auto()
    FILE_SYMBOLS = auto()
    SUBGRAPH = auto()
    MANUAL = auto()


@dataclass(frozen=True)
class ObservedSymbol:
    agent_id: str
    symbol: str
    interface_hash: int | None
    body_hash: int | None
    source: ObservationSource
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class StaleSymbol:
    symbol: str
    observed_interface_hash: int | None
    current_interface_hash: int | None
    observed_body_hash: int | None
    current_body_hash: int | None
    reason: str


@dataclass(frozen=True)
class StaleContextReport:
    agent_id: str
    stale_symbols: tuple[StaleSymbol, ...]


@dataclass(frozen=True)
class AgentSession:
    agent_id: str
    name: str
    task: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def payload(self) -> dict[str, object]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "task": self.task,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen_at": self.last_seen_at.strftime("%Y-%m-%d %H:%M:%S"),
        }


def new_id() -> str:
    return uuid4().hex
