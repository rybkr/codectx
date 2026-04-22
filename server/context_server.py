from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pathlib import Path
import json

from server.events import EventBus, ContextEvent
from context import ContextService
from context.models import FileUpdate
from server.models import (
    TaskQueryRequest,
    SubgraphRequest,
    InvalidateRequest,
    FileUpdatesRequest,
    RegisterAgentRequest,
)


def create_app(root: Path) -> FastAPI:
    service: ContextService = ContextService(root=root)
    events: EventBus = EventBus()
    app: FastAPI = FastAPI(title="CodeCtx Context Server")

    @app.on_event("startup")
    async def _startup() -> None:
        report = await service.build()
        await events.publish(ContextEvent(kind="graph_built", payload=report.payload))

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "root": str(service.root),
            "symbols": len(service.all_symbols()),
        }

    @app.get("/symbols")
    async def list_symbols() -> list[dict[str, object]]:
        return [record.payload for record in service.all_symbols()]

    @app.get("/symbols/{symbol:path}")
    async def get_symbol(symbol: str, agent_id: str | None = None) -> dict[str, object]:
        details = service.symbol_details(symbol, agent_id=agent_id)
        if details is None:
            raise HTTPException(status_code=404, detail="symbol not found")
        return details.payload

    @app.get("/files")
    async def file_symbols(path: str, agent_id: str | None = None) -> dict[str, object]:
        try:
            records = service.symbols_in_file(Path(path), agent_id=agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "path": path,
            "symbols": [record.payload for record in records],
        }

    @app.post("/tasks/relevant-symbols")
    async def relevant_symbols(request: TaskQueryRequest) -> dict[str, object]:
        records = service.relevant_symbols_for_task(
            request.task, limit=request.limit, agent_id=request.agent_id
        )
        return {
            "task": request.task,
            "symbols": [record.payload for record in records],
        }

    @app.post("/subgraph")
    async def subgraph(request: SubgraphRequest) -> dict[str, object]:
        graph = service.subgraph_for_symbols(
            request.symbols, depth=request.depth, agent_id=request.agent_id
        )
        return graph.payload

    @app.post("/invalidate")
    async def invalidate(request: InvalidateRequest) -> dict[str, object]:
        report = service.invalidate_symbols(set(request.changed_symbols))
        payload = report.payload
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
        payload = report.payload
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

    @app.post("/agents/register")
    async def register_agent(request: RegisterAgentRequest) -> dict[str, object]:
        return service.register_agent(request.name, request.task).payload

    @app.post("/agents/{agent_id}/heartbeat")
    async def heartbeat(agent_id: str) -> dict[str, object]:
        session = service.heartbeat(agent_id)
        if session is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return session.payload

    @app.get("/agents/{agent_id}/stale-context")
    async def stale_context(agent_id: str) -> dict[str, object]:
        try:
            return service.stale_context(agent_id).payload
        except KeyError:
            raise HTTPException(status_code=404, detail="agent not found")

    return app
