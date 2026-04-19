from __future__ import annotations

import argparse
import logging
import re
import socket
import subprocess
from pathlib import Path

MARKER_START = "<!-- codectx-context-server:start -->"
MARKER_END = "<!-- codectx-context-server:end -->"

log = logging.getLogger("cli.instructions")


def resolve_instructions_path(root: Path, requested: str | None) -> Path:
    if requested:
        return root / requested

    for candidate in ("AGENTS.md", "CLAUDE.md"):
        path = root / candidate
        if path.exists():
            return path
    return root / "AGENTS.md"


def server_guidance(base_url: str) -> str:
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
            f'- task symbols: `curl -sS -X POST {base_url}/tasks/relevant-symbols -H \'content-type: application/json\' -d \'{{"task":"update the context server client","limit":8}}\'`',
            f"- file symbols: `curl -sS '{base_url}/files?path=main.py'`",
            f"- symbol detail: `curl -sS '{base_url}/symbols/main.serve'`",
            f'- subgraph: `curl -sS -X POST {base_url}/subgraph -H \'content-type: application/json\' -d \'{{"symbols":["main.serve"],"depth":1}}\'`',
            f'- file update: `curl -sS -X POST {base_url}/updates/files -H \'content-type: application/json\' -d \'{{"updates":[{{"path":"main.py","before":"old source here","after":"new source here"}}]}}\'`',
            "",
            "Recovery and safety:",
            "- if local reasoning conflicts with server state, trust the server",
            f"- call `POST {base_url}/reset` only for operator recovery to rebuild server state from disk, not as part of normal agent flow",
            MARKER_END,
        ]
    )


def detect_lan_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        if address and not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        sock.close()

    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    address = result.stdout.strip()
    if not address or address.startswith("127."):
        return None
    return address


def instruction_base_url(args: argparse.Namespace) -> str:
    public_url = getattr(args, "public_url", None)
    if public_url:
        return public_url.rstrip("/")

    if args.host in {"0.0.0.0", "::"}:
        address = detect_lan_ip()
        if address:
            return f"http://{address}:{args.port}"
        log.warning(
            "could not determine a reachable host automatically; "
            "use --public-url to override the injected server URL"
        )
        return f"http://127.0.0.1:{args.port}"

    return f"http://{args.host}:{args.port}"


def remove_marked_block(contents: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}\n?",
        flags=re.DOTALL,
    )
    updated = pattern.sub("\n", contents)
    return updated.rstrip() + ("\n" if updated.strip() else "")


def ensure_server_guidance(args: argparse.Namespace, root: Path) -> Path | None:
    target = resolve_instructions_path(root, args.instructions_file)
    contents = target.read_text(encoding="utf-8") if target.exists() else ""

    block = server_guidance(instruction_base_url(args))
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

    if not args.inject_guidance:
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


def remove_server_guidance(root: Path, target: Path | None) -> None:
    if target is None or not target.exists():
        return

    contents = target.read_text(encoding="utf-8")
    if MARKER_START not in contents or MARKER_END not in contents:
        return

    updated = remove_marked_block(contents)
    if updated:
        target.write_text(updated, encoding="utf-8")
        log.info("removed server guidance from %s", target.relative_to(root))
        return

    target.unlink()
    log.info("removed empty instructions file %s", target.relative_to(root))
