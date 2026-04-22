from pydantic import BaseModel, Field
from pathlib import Path


class TaskQueryRequest(BaseModel):
    task: str
    limit: int = Field(default=10, ge=1, le=100)
    agent_id: str | None = None


class SubgraphRequest(BaseModel):
    symbols: list[str]
    depth: int = Field(default=1, ge=0, le=5)
    agent_id: str | None = None


class InvalidateRequest(BaseModel):
    changed_symbols: list[str]


class FileUpdatePayload(BaseModel):
    path: Path
    before: bytes
    after: bytes


class FileUpdatesRequest(BaseModel):
    updates: list[FileUpdatePayload]


class RegisterAgentRequest(BaseModel):
    name: str
    task: str


class AgentQuery(BaseModel):
    agent_id: str | None = None
