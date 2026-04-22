from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.models import (
    BuildReport,
    ContextSubgraph,
    EditResult,
    FileUpdate,
    ImpactReport,
    Symbol,
    SymbolDetails,
)
from core.service import ContextService


class TaskQueryRequest(BaseModel):
    task: str
    limit: int = Field(default=10, ge=1, le=100)


class SubgraphRequest(BaseModel):
    symbols: list[str]
    depth: int = Field(default=1, ge=0, le=5)


class InvalidateRequest(BaseModel):
    changed_symbols: list[str]


class FileUpdatePayload(BaseModel):
    path: str
    before: str
    after: str


class FileUpdatesRequest(BaseModel):
    updates: list[FileUpdatePayload]


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


def create_app(root: Path) -> FastAPI:
    service = ContextService(root=root)
    events = EventBus()
    app = FastAPI(title="CodeCtx Context Graph Server")

    @app.on_event("startup")
    async def _startup() -> None:
        report = await service.build()
        await events.publish(
            ContextEvent(kind="graph_built", payload=_build_report_to_dict(report))
        )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "root": str(service.root),
            "symbols": len(service.all_symbols()),
        }

    @app.post("/reset")
    async def reset() -> dict[str, object]:
        report = await service.reset()
        payload = _build_report_to_dict(report)
        await events.publish(ContextEvent(kind="graph_reset", payload=payload))
        return {"status": "ok", **payload}

    @app.get("/symbols")
    async def list_symbols() -> list[dict[str, object]]:
        return [_symbol_to_dict(record) for record in service.all_symbols()]

    @app.get("/symbols/{symbol:path}")
    async def get_symbol(symbol: str) -> dict[str, object]:
        details = service.symbol_details(symbol)
        if details is None:
            raise HTTPException(status_code=404, detail="symbol not found")
        return _symbol_details_to_dict(details)

    @app.get("/files")
    async def file_symbols(path: str) -> dict[str, object]:
        try:
            records = service.symbols_in_file(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "path": path,
            "symbols": [_symbol_to_dict(record) for record in records],
        }

    @app.post("/tasks/relevant-symbols")
    async def relevant_symbols(request: TaskQueryRequest) -> dict[str, object]:
        records = service.relevant_symbols_for_task(request.task, limit=request.limit)
        return {
            "task": request.task,
            "symbols": [_symbol_to_dict(record) for record in records],
        }

    @app.post("/subgraph")
    async def subgraph(request: SubgraphRequest) -> dict[str, object]:
        graph = service.subgraph_for_symbols(request.symbols, depth=request.depth)
        return _subgraph_to_dict(graph)

    @app.post("/invalidate")
    async def invalidate(request: InvalidateRequest) -> dict[str, object]:
        report = service.invalidate_symbols(request.changed_symbols)
        payload = _impact_report_to_dict(report)
        event_payload = {
            "changed_symbols": payload["changed_symbols"],
            "impacted_symbols": payload["impacted_symbols"],
        }
        await events.publish(
            ContextEvent(kind="symbols_invalidated", payload=event_payload)
        )
        return event_payload

    @app.post("/updates/files")
    async def update_files(request: FileUpdatesRequest) -> dict[str, object]:
        try:
            report = service.apply_file_updates(
                [
                    FileUpdate(
                        path=update.path,
                        before=update.before,
                        after=update.after,
                    )
                    for update in request.updates
                ]
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = _impact_report_to_dict(report)
        await events.publish(ContextEvent(kind="files_updated", payload=payload))
        return payload

    @app.get("/events")
    async def stream_events() -> StreamingResponse:
        queue = await events.subscribe()

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
                await events.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _build_report_to_dict(report: BuildReport) -> dict[str, object]:
    return {
        "root": report.root,
        "symbols": report.symbols,
    }


def _symbol_to_dict(record: Symbol) -> dict[str, object]:
    return {
        "symbol": record.symbol,
        "kind": record.kind.value,
        "interface_hash": record.interface_hash,
    }


def _symbol_details_to_dict(details: SymbolDetails) -> dict[str, object]:
    return {
        "record": _symbol_to_dict(details.record),
        "dependencies": [_symbol_to_dict(item) for item in details.dependencies],
        "dependents": [_symbol_to_dict(item) for item in details.dependents],
    }


def _subgraph_to_dict(graph: ContextSubgraph) -> dict[str, object]:
    return {
        "center_symbols": list(graph.center_symbols),
        "nodes": list(graph.nodes),
        "edges": [[source, target] for source, target in graph.edges],
    }


def _edit_to_dict(edit: EditResult) -> dict[str, object]:
    return {
        "symbol": edit.symbol,
        "kind": edit.kind.value,
        "old_interface": None
        if edit.old_interface is None
        else edit.old_interface.decode("utf-8", errors="replace"),
        "new_interface": None
        if edit.new_interface is None
        else edit.new_interface.decode("utf-8", errors="replace"),
    }


def _impact_report_to_dict(report: ImpactReport) -> dict[str, object]:
    return {
        "paths": list(report.paths),
        "edits": [_edit_to_dict(edit) for edit in report.edits],
        "changed_symbols": list(report.changed_symbols),
        "impacted_symbols": list(report.impacted_symbols),
    }
