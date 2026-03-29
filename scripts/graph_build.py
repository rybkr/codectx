import argparse
import asyncio
from pathlib import Path


async def run(args: argparse.Namespace) -> None:
    from graph.dependency_graph import DependencyGraph

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"error: path does not exist: {root}")

    graph = DependencyGraph(root=root)
    await graph.build()
    print(f"\nnodes : {graph._g.number_of_nodes()}")
    print(f"edges : {graph._g.number_of_edges()}")
    print(f"symbols: {list(graph._symbols)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.graph_build",
        description="build dependency graph and print stats",
    )
    parser.add_argument("root", help="path to codebase root")
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
