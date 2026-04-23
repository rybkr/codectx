from __future__ import annotations

import asyncio
from argparse import Namespace
from pathlib import Path


async def run_http(args: Namespace) -> int:
    import uvicorn

    from server.context_server import create_app

    root: Path = Path(args.root).resolve()
    app = create_app(root)

    config = uvicorn.Config(app, host=args.host, port=args.port)
    server = uvicorn.Server(config)
    await server.serve()

    return 0


def run_mcp(args: Namespace) -> int:
    import asyncio

    from mcp_server import MCPServer

    root: Path = Path(args.root).resolve()
    server = MCPServer(root)
    asyncio.run(server.build())
    server.run()

    return 0


def register(subparsers, formatter_class) -> None:
    parser = subparsers.add_parser(
        "serve",
        help="Serve CodeCtx over HTTP or MCP",
        description="Start a CodeCtx runtime server.",
        formatter_class=formatter_class,
    )

    serve_subparsers = parser.add_subparsers(dest="serve_command", metavar="command")
    serve_subparsers.required = True

    http = serve_subparsers.add_parser(
        "http",
        help="Serve the HTTP API",
        formatter_class=formatter_class,
    )
    http.add_argument("root", nargs="?", default=".")
    http.add_argument("--host", default="127.0.0.1")
    http.add_argument("--port", type=int, default=27962)
    http.set_defaults(handler=run_http)

    mcp = serve_subparsers.add_parser(
        "mcp",
        help="Serve the MCP tool server",
        formatter_class=formatter_class,
    )
    mcp.add_argument("root", nargs="?", default=".")
    mcp.set_defaults(handler=run_mcp)
