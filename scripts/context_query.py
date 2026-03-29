import argparse
import asyncio
from pathlib import Path


async def run(args: argparse.Namespace) -> None:
    from graph.context_graph import ContextGraph
    from graph.dependency_graph import DependencyGraph

    root = Path(args.root)
    graph = DependencyGraph(root=root)
    context = ContextGraph(graph)
    await context.build()

    if args.file:
        records = context.symbols_in_file(args.file)
        print(f"\nfile : {args.file}")
        print(f"symbols ({len(records)}):")
        for record in records:
            print(f" {record.symbol} [{record.kind}]")
        return

    if args.task:
        records = context.relevant_symbols_for_task(args.task, limit=args.limit)
        print(f"\ntask : {args.task}")
        print(f"relevant symbols ({len(records)}):")
        for record in records:
            print(f" {record.symbol} [{record.kind}]")
        return

    if args.symbol:
        subgraph = context.subgraph_for_symbols([args.symbol], depth=args.depth)
        print(f"\nsymbol : {args.symbol}")
        print(f"nodes ({len(subgraph.nodes)}):")
        for node in subgraph.nodes:
            print(f" {node}")
        print(f"edges ({len(subgraph.edges)}):")
        for source, target in subgraph.edges:
            print(f" {source} -> {target}")
        return

    raise SystemExit("error: provide one of --file, --task, or --symbol")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.context_query",
        description="query the shared context graph locally",
    )
    parser.add_argument("root", help="path to codebase root")
    parser.add_argument("--file", help="repo-relative python file to inspect")
    parser.add_argument("--task", help="task text to rank relevant symbols for")
    parser.add_argument("--symbol", help="symbol to expand into a local context subgraph")
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="subgraph expansion depth for --symbol",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="max symbols to return for --task",
    )
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
