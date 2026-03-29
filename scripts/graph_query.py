import argparse
import asyncio
from pathlib import Path


async def run(args: argparse.Namespace) -> None:
    from graph.dependency_graph import DependencyGraph

    root = Path(args.root)
    graph = DependencyGraph(root=root)
    await graph.build()
    symbol = args.symbol
    deps = graph.dependents(symbol)
    iface = graph.interface_hash(symbol)
    print(f"\nsymbol : {symbol}")
    print(f"interface hash : {iface}")
    print(f"dependents ({len(deps)}): ")
    for dependent in sorted(deps):
        print(f" {dependent}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.graph_query",
        description="query dependents of a symbol",
    )
    parser.add_argument("root", help="path to codebase root")
    parser.add_argument("symbol", help="qualified symbol e.g. mymodule.my_function")
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
