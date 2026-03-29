from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph.context_graph import ContextGraph, ContextSubgraph, SymbolRecord
from graph.dependency_graph import DependencyGraph


class TaskQueryRequest(BaseModel):
    task: str
    limit: int = Field(default=12, ge=1, le=100)


class SubgraphRequest(BaseModel):
    symbols: list[str]
    depth: int = Field(default=1, ge=0, le=5)


class InvalidateRequest(BaseModel):
    changed_symbols: list[str]


@dataclass(frozen=True)
class ContextEvent:
    kind: str
    payload: dict[str, Any]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[ContextEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: ContextEvent) -> None:
        async with self._lock:
            for queue in list(self._subscribers):
                await queue.put(event)

    async def subscribe(self) -> asyncio.Queue[ContextEvent]:
        queue: asyncio.Queue[ContextEvent] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[ContextEvent]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)


class ContextService:
    def __init__(self, root: Path):
        self.root = root
        self.context = ContextGraph(DependencyGraph(root=root))
        self.events = EventBus()

    async def build(self) -> None:
        await self.context.build()
        await self.events.publish(
            ContextEvent(
                kind="graph_built",
                payload={
                    "root": str(self.root),
                    "symbols": len(self.context.all_symbols()),
                },
            )
        )

    async def invalidate(self, changed_symbols: list[str]) -> list[str]:
        impacted = self.context.invalidate_from_changes(changed_symbols)
        await self.events.publish(
            ContextEvent(
                kind="symbols_invalidated",
                payload={
                    "changed_symbols": changed_symbols,
                    "impacted_symbols": impacted,
                },
            )
        )
        return impacted


def create_app(root: Path) -> FastAPI:
    service = ContextService(root=root)
    app = FastAPI(title="Async Context Graph Server")

    @app.on_event("startup")
    async def _startup() -> None:
        await service.build()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "root": str(service.root),
            "symbols": len(service.context.all_symbols()),
        }

    @app.get("/symbols")
    async def list_symbols() -> list[dict[str, object]]:
        return [_symbol_to_dict(record) for record in service.context.all_symbols()]

    @app.get("/symbols/{symbol:path}")
    async def get_symbol(symbol: str) -> dict[str, object]:
        record = service.context.symbol(symbol)
        if record is None:
            raise HTTPException(status_code=404, detail="symbol not found")
        return {
            "record": _symbol_to_dict(record),
            "dependencies": [_symbol_to_dict(item) for item in service.context.dependencies(symbol)],
            "dependents": [_symbol_to_dict(item) for item in service.context.dependents(symbol)],
        }

    @app.get("/files")
    async def file_symbols(path: str) -> dict[str, object]:
        try:
            records = service.context.symbols_in_file(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"path": path, "symbols": [_symbol_to_dict(record) for record in records]}

    @app.post("/tasks/relevant-symbols")
    async def relevant_symbols(request: TaskQueryRequest) -> dict[str, object]:
        records = service.context.relevant_symbols_for_task(request.task, limit=request.limit)
        return {
            "task": request.task,
            "symbols": [_symbol_to_dict(record) for record in records],
        }

    @app.post("/subgraph")
    async def subgraph(request: SubgraphRequest) -> dict[str, object]:
        graph = service.context.subgraph_for_symbols(request.symbols, depth=request.depth)
        return _subgraph_to_dict(graph)

    @app.post("/invalidate")
    async def invalidate(request: InvalidateRequest) -> dict[str, object]:
        impacted = await service.invalidate(request.changed_symbols)
        return {
            "changed_symbols": request.changed_symbols,
            "impacted_symbols": impacted,
        }

    @app.get("/events")
    async def events() -> StreamingResponse:
        queue = await service.events.subscribe()

        async def stream():
            try:
                while True:
                    event = await queue.get()
                    payload = json.dumps(
                        {"kind": event.kind, "payload": event.payload},
                        sort_keys=True,
                    )
                    yield f"data: {payload}\n\n"
            finally:
                await service.events.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _symbol_to_dict(record: SymbolRecord) -> dict[str, object]:
    return asdict(record)


def _subgraph_to_dict(graph: ContextSubgraph) -> dict[str, object]:
    return {
        "center_symbols": list(graph.center_symbols),
        "nodes": list(graph.nodes),
        "edges": [[source, target] for source, target in graph.edges],
    }
