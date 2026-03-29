from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from graph.context_graph import ContextSubgraph, SymbolRecord


@dataclass(frozen=True)
class FileUpdateRequest:
    path: str
    before: str
    after: str


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

    def all_symbols(self) -> list[SymbolRecord]:
        payload = self._get_json("/symbols")
        return [_symbol_record(item) for item in payload]

    def symbol(self, symbol: str) -> dict[str, Any]:
        payload = self._get_json(f"/symbols/{symbol}")
        return {
            "record": _symbol_record(payload["record"]),
            "dependencies": [_symbol_record(item) for item in payload["dependencies"]],
            "dependents": [_symbol_record(item) for item in payload["dependents"]],
        }

    def symbols_in_file(self, path: str) -> list[SymbolRecord]:
        payload = self._get_json("/files", params={"path": path})
        return [_symbol_record(item) for item in payload["symbols"]]

    def relevant_symbols_for_task(self, task: str, limit: int = 12) -> list[SymbolRecord]:
        payload = self._post_json(
            "/tasks/relevant-symbols",
            json={"task": task, "limit": limit},
        )
        return [_symbol_record(item) for item in payload["symbols"]]

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
        updates: list[FileUpdateRequest],
    ) -> dict[str, Any]:
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
        return payload

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


def _symbol_record(payload: dict[str, Any]) -> SymbolRecord:
    return SymbolRecord(
        symbol=payload["symbol"],
        kind=payload["kind"],
        interface_hash=payload["interface_hash"],
    )
