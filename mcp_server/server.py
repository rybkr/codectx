from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pathlib import Path

from context import ContextService
from context.models import FileUpdate


class MCPServer:
    def __init__(self, root: Path):
        self._service = ContextService(root)
        self._mcp = FastMCP("codectx")
        self.register_tools()

    async def build(self) -> None:
        await self._service.build()

    def register_tools(self) -> None:
        @self._mcp.tool()
        def codectx_register_agent(name: str, task: str) -> dict[str, object]:
            return self._service.register_agent(name, task).payload

        @self._mcp.tool()
        def codectx_relevant_symbols(
            agent_id: str, task: str, limit: int = 10
        ) -> dict[str, object]:
            symbols = self._service.relevant_symbols_for_task(
                task, limit=limit, agent_id=agent_id
            )
            return {"symbols": [symbol.payload for symbol in symbols]}

        @self._mcp.tool()
        def codectx_symbol_details(
            agent_id: str,
            symbol: str,
        ) -> dict[str, object]:
            details = self._service.symbol_details(symbol, agent_id=agent_id)
            if details is None:
                return {"error": "symbol not found", "symbol": symbol}
            return details.payload

        @self._mcp.tool()
        def codectx_apply_file_update(
            path: str,
            before: str,
            after: str,
        ) -> dict[str, object]:
            report = self._service.apply_file_updates(
                [
                    FileUpdate(
                        path=Path(path),
                        before=before.encode("utf-8"),
                        after=after.encode("utf-8"),
                    )
                ]
            )
            return report.payload

        @self._mcp.tool()
        def codectx_stale_context(agent_id: str) -> dict[str, object]:
            return self._service.stale_context(agent_id).payload
