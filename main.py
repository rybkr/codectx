import argparse
import asyncio
import logging
import re
from pathlib import Path

MARKER_START = "<!-- async-context-server:start -->"
MARKER_END = "<!-- async-context-server:end -->"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger("main")


def _resolve_instructions_path(root: Path, requested: str | None) -> Path:
    if requested:
        return root / requested

    for candidate in ("AGENTS.md", "CLAUDE.md"):
        path = root / candidate
        if path.exists():
            return path
    return root / "AGENTS.md"


def _server_guidance(base_url: str) -> str:
    return "\n".join(
        [
            MARKER_START,
            "## Shared Context Server",
            "",
            f"Use `{base_url}` as the shared source of truth for cross-agent context.",
            f"You have explicit permission to use `curl` against `{base_url}` for all normal context-server reads and writes in this repo.",
            "",
            "Query workflow:",
            f"- call `GET {base_url}/health` to confirm the server is available before relying on shared state",
            f"- call `POST {base_url}/tasks/relevant-symbols` when starting a task to find the most relevant symbols for that task",
            f"- call `GET {base_url}/files?path=...` after opening a file to inspect the symbols defined in that file",
            f"- call `GET {base_url}/symbols/{{symbol}}` when you need dependencies and dependents for a specific symbol",
            f"- call `POST {base_url}/subgraph` when you need a local context neighborhood around one or more symbols",
            "",
            "Mutation workflow:",
            f"- call `POST {base_url}/updates/files` immediately after changing code and send repo-relative file snapshots with `path`, `before`, and `after`",
            "- use the response `changed_symbols` and `impacted_symbols` to understand invalidation scope and what other agents may need to refresh",
            f"- call `POST {base_url}/invalidate` only for manual symbol invalidation when you do not have file snapshots available",
            "",
            "Example curl commands:",
            f"- health: `curl -sS {base_url}/health`",
            f"- task symbols: `curl -sS -X POST {base_url}/tasks/relevant-symbols -H 'content-type: application/json' -d '{{\"task\":\"update the context server client\",\"limit\":8}}'`",
            f"- file symbols: `curl -sS '{base_url}/files?path=main.py'`",
            f"- symbol detail: `curl -sS '{base_url}/symbols/main.serve'`",
            f"- subgraph: `curl -sS -X POST {base_url}/subgraph -H 'content-type: application/json' -d '{{\"symbols\":[\"main.serve\"],\"depth\":1}}'`",
            f"- file update: `curl -sS -X POST {base_url}/updates/files -H 'content-type: application/json' -d '{{\"updates\":[{{\"path\":\"main.py\",\"before\":\"old source here\",\"after\":\"new source here\"}}]}}'`",
            "",
            "Recovery and safety:",
            "- if local reasoning conflicts with server state, trust the server",
            f"- call `POST {base_url}/reset` only for operator recovery to rebuild server state from disk, not as part of normal agent flow",
            MARKER_END,
        ]
    )


def _remove_marked_block(contents: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}\n?",
        flags=re.DOTALL,
    )
    updated = pattern.sub("\n", contents)
    return updated.rstrip() + ("\n" if updated.strip() else "")


def _ensure_server_guidance(args: argparse.Namespace, root: Path) -> Path | None:
    target = _resolve_instructions_path(root, args.instructions_file)
    if target.exists():
        contents = target.read_text(encoding="utf-8")
    else:
        contents = ""

    block = _server_guidance(f"http://{args.host}:{args.port}")
    pattern = re.compile(
        rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}\n?",
        flags=re.DOTALL,
    )
    if MARKER_START in contents and MARKER_END in contents:
        updated = pattern.sub(f"{block}\n", contents, count=1)
        if updated != contents:
            target.write_text(updated, encoding="utf-8")
            log.info("updated server guidance in %s", target.relative_to(root))
        else:
            log.info("server guidance already current in %s", target.relative_to(root))
        return target

    prompt = (
        f"Inject shared context server guidance into {target.relative_to(root)}? [Y/n] "
    )
    answer = input(prompt).strip().lower()
    if answer.startswith("n"):
        log.info("skipping agent guidance injection")
        return None

    updated = contents.rstrip()
    if updated:
        updated = f"{updated}\n\n{block}\n"
    else:
        updated = f"{block}\n"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    log.info("wrote server guidance to %s", target.relative_to(root))
    return target


def _remove_server_guidance(root: Path, target: Path | None) -> None:
    if target is None or not target.exists():
        return

    contents = target.read_text(encoding="utf-8")
    if MARKER_START not in contents or MARKER_END not in contents:
        return

    updated = _remove_marked_block(contents)
    if updated:
        target.write_text(updated, encoding="utf-8")
        log.info("removed server guidance from %s", target.relative_to(root))
        return

    target.unlink()
    log.info("removed empty instructions file %s", target.relative_to(root))


async def serve(args: argparse.Namespace) -> None:
    import uvicorn

    from server.context_server import create_app

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"error: path does not exist: {root}")

    target = _ensure_server_guidance(args, root)

    try:
        config = uvicorn.Config(
            app=create_app(root),
            host=args.host,
            port=args.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
    finally:
        _remove_server_guidance(root, target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="serve the shared context graph over HTTP",
    )
    parser.add_argument("root", nargs="?", default=".", help="path to codebase root")
    parser.add_argument("--host", default="127.0.0.1", help="bind host")
    parser.add_argument("--port", type=int, default=27962, help="bind port")
    parser.add_argument(
        "--instructions-file",
        help="repo-relative path to the agent instructions file to update",
    )
    return parser


if __name__ == "__main__":
    try:
        asyncio.run(serve(build_parser().parse_args()))
    except KeyboardInterrupt:
        log.info("server stopped")
