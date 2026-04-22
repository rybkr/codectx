from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

from cli.output import print_heading, print_kv, print_list


def _graph_export(
    root: Path, graph
) -> tuple[dict[str, object], list[dict[str, object]]]:
    metadata: dict = {
        "type": "metadata",
        "root": str(root.resolve()),
        "nodes": graph.symbol_count(),
        "edges": graph.ref_count(),
        "format": "codectx.symbol_graph.v2",
    }
    nodes: list[dict[str, object]] = []

    for symbol in graph.symbol_items():
        nodes.append(
            {
                "type": "node",
                "symbol": symbol.qname,
                "kind": symbol.kind,
                "interface_hash": symbol.interface_hash,
                "dependencies": graph.successors(symbol.qname),
            }
        )

    return metadata, nodes


async def run_build(args: Namespace) -> int:
    from graph.symbol_graph import SymbolGraph

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"error: path does not exist: {root}")

    graph = SymbolGraph(root=root)
    await graph.build()

    metadata, nodes = _graph_export(root, graph)
    lines = [json.dumps(metadata, sort_keys=True)]
    lines.extend(json.dumps(node, sort_keys=True) for node in nodes)

    payload = "\n".join(lines) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
        print(f"wrote NDJSON graph to {output_path}", file=sys.stderr)
        return 0

    try:
        sys.stdout.write(payload)
    except BrokenPipeError:
        pass

    return 0


async def run_dependents(args: Namespace) -> int:
    from graph.symbol_graph import SymbolGraph

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"error: path does not exist: {root}")

    graph = SymbolGraph(root=root)
    await graph.build()

    dependents = sorted(graph.dependents(args.symbol))
    print_heading("Symbol Dependents")
    print_kv("Root", root)
    print_kv("Symbol", args.symbol)
    print_kv("Interface Hash", graph.interface_hash(args.symbol))
    print()
    print_list("Dependents", dependents)
    return 0


def register(subparsers, formatter_class) -> None:
    parser = subparsers.add_parser(
        "graph",
        help="Inspect symbol graph structure",
        description="Build and inspect the repository symbol graph.",
        formatter_class=formatter_class,
    )
    graph_subparsers = parser.add_subparsers(dest="graph_command", metavar="command")
    graph_subparsers.required = True

    build_parser = graph_subparsers.add_parser(
        "build",
        help="Build the symbol graph and export it as NDJSON",
        description=(
            "Build the symbol graph for a repository and export it as NDJSON. "
            "The first line is metadata and each subsequent line is a node record."
        ),
        formatter_class=formatter_class,
    )
    build_parser.add_argument(
        "root", nargs="?", default=".", help="Path to the codebase root"
    )
    build_parser.add_argument(
        "-o",
        "--output",
        help="Write NDJSON output to a file instead of stdout",
    )
    build_parser.set_defaults(handler=run_build)

    dependents_parser = graph_subparsers.add_parser(
        "dependents",
        help="Show dependents of a symbol",
        description="Show the transitive dependents for a symbol in the symbol graph.",
        formatter_class=formatter_class,
    )
    dependents_parser.add_argument(
        "root", nargs="?", default=".", help="Path to the codebase root"
    )
    dependents_parser.add_argument("symbol", help="Qualified symbol name")
    dependents_parser.set_defaults(handler=run_dependents)
