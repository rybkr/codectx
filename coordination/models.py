from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum, auto
from uuid import uuid4


class ClaimMode(StrEnum):
    READ = auto()
    WRITE = auto()


@dataclass(frozen=True)
class AgentSession:
    id: str
    name: str
    task: str
    started_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class Claim:
    id: str
    agent_id: str
    symbols: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    mode: ClaimMode = ClaimMode.WRITE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=60)
    )


@dataclass(frozen=True)
class Observation:
    agent_id: str
    symbols: tuple[str, ...]
    source: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def new_id() -> str:
    return uuid4().hex
