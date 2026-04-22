from __future__ import annotations

from typing import Any

import httpx

from core.models import (
    ContextSubgraph,
    EditKind,
    EditResult,
    FileUpdate,
    ImpactReport,
    Symbol,
    SymbolDetails,
    SymbolKind,
)


class ContextHttpClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:27962",
        *,
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._get_json("/health")

    def reset(self) -> dict[str, Any]:
        return self._post_json("/reset", json={})

    def all_symbols(self) -> list[Symbol]:
        payload = self._get_json("/symbols")
        return [_symbol(item) for item in payload]

    def symbol(self, symbol: str) -> SymbolDetails:
        payload = self._get_json(f"/symbols/{symbol}")
        return SymbolDetails(
            record=_symbol(payload["record"]),
            dependencies=tuple(_symbol(item) for item in payload["dependencies"]),
            dependents=tuple(_symbol(item) for item in payload["dependents"]),
        )

    def symbols_in_file(self, path: str) -> list[Symbol]:
        payload = self._get_json("/files", params={"path": path})
        return [_symbol(item) for item in payload["symbols"]]

    def relevant_symbols_for_task(self, task: str, limit: int = 12) -> list[Symbol]:
        payload = self._post_json(
            "/tasks/relevant-symbols",
            json={"task": task, "limit": limit},
        )
        return [_symbol(item) for item in payload["symbols"]]

    def subgraph_for_symbols(
        self,
        symbols: list[str],
        *,
        depth: int = 1,
    ) -> ContextSubgraph:
        payload = self._post_json(
            "/subgraph",
            json={"symbols": symbols, "depth": depth},
        )
        return ContextSubgraph(
            center_symbols=tuple(payload["center_symbols"]),
            nodes=tuple(payload["nodes"]),
            edges=tuple((source, target) for source, target in payload["edges"]),
        )

    def invalidate(self, changed_symbols: list[str]) -> list[str]:
        payload = self._post_json(
            "/invalidate",
            json={"changed_symbols": changed_symbols},
        )
        return list(payload["impacted_symbols"])

    def apply_file_updates(
        self,
        updates: list[FileUpdate],
    ) -> ImpactReport:
        payload = self._post_json(
            "/updates/files",
            json={
                "updates": [
                    {
                        "path": update.path,
                        "before": update.before,
                        "after": update.after,
                    }
                    for update in updates
                ]
            },
        )
        return ImpactReport(
            paths=tuple(payload["paths"]),
            edits=tuple(_edit(item) for item in payload["edits"]),
            changed_symbols=tuple(payload["changed_symbols"]),
            impacted_symbols=tuple(payload["impacted_symbols"]),
        )

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            return response.json()

    def _post_json(self, path: str, *, json: dict[str, Any]) -> Any:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
            response = client.post(path, json=json)
            response.raise_for_status()
            return response.json()


def _symbol(payload: dict[str, Any]) -> Symbol:
    raw_kind = payload.get("kind", SymbolKind.UNKNOWN.value)
    try:
        kind = SymbolKind(raw_kind)
    except ValueError:
        kind = SymbolKind.UNKNOWN
    return Symbol(
        symbol=payload["symbol"],
        kind=kind,
        interface_hash=payload["interface_hash"],
    )


def _edit(payload: dict[str, Any]):
    raw_kind = payload.get("kind", EditKind.INTERNAL.value)
    try:
        kind = EditKind(raw_kind)
    except ValueError:
        kind = EditKind.INTERNAL
    return EditResult(
        symbol=payload["symbol"],
        kind=kind,
        old_interface=None
        if payload["old_interface"] is None
        else payload["old_interface"].encode("utf-8"),
        new_interface=None
        if payload["new_interface"] is None
        else payload["new_interface"].encode("utf-8"),
    )


__all__ = ["ContextHttpClient", "FileUpdate"]
