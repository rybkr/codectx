import asyncio
import logging
from pathlib import Path
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger("main")


async def cmd_graph_build(args: argparse.Namespace) -> None:
    from graph.dependency_graph import DependencyGraph

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"error: path does not exist: {root}")
    log.info("building graph for %s", root)
    graph = DependencyGraph(root=root)
    await graph.build()
    print(f"\nnodes : {graph._g.number_of_nodes()}")
    print(f"edges : {graph._g.number_of_edges()}")
    print(f"symbols: {list(graph._symbols)[:10]} ...")


async def cmd_graph_query(args: argparse.Namespace) -> None:
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
    for d in sorted(deps):
        print(f" {d}")


async def cmd_run(args: argparse.Namespace) -> None:
    import yaml
    from agents.coding_agent import CodingAgent
    from graph.dependency_graph import DependencyGraph
    from detection.commit_watcher import CommitWatcher
    from detection.invalidation_engine import InvalidationEngine
    from detection.context_manager import ContextManager
    from experiments.harness import ExperimentHarness

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    graph = DependencyGraph(root=Path(cfg["codebase_root"]))
    await graph.build()
    agents = [
        CodingAgent(id=i, worktree=Path(wt), graph=graph, cfg=cfg)
        for i, wt in enumerate(cfg["worktrees"])
    ]
    ctx_mgr = ContextManager(agents=agents)
    engine = InvalidationEngine(graph=graph, context_manager=ctx_mgr)
    watcher = CommitWatcher(worktrees=cfg["worktrees"], engine=engine)
    if cfg.get("mode") == "experiment":
        await ExperimentHarness(agents=agents, watcher=watcher, cfg=cfg).run()
    else:
        await asyncio.gather(watcher.watch(), *[a.run() for a in agents])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cv", description="context-validity toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    gb = sub.add_parser("graph:build", help="build dependency graph and print stats")
    gb.add_argument("root", help="path to codebase root")

    gq = sub.add_parser("graph:query", help="query dependents of a symbol")
    gq.add_argument("root", help="path to codebase root")
    gq.add_argument("symbol", help="qualified symbol e.g. mymodule.my_function")

    rn = sub.add_parser("run", help="run full multi-agent pipeline")
    rn.add_argument("--config", default="config.yaml", help="path to config.yaml")

    return p


_COMMANDS = {
    "graph:build": cmd_graph_build,
    "graph:query": cmd_graph_query,
    "run": cmd_run,
}

if __name__ == "__main__":
    args = build_parser().parse_args()
    asyncio.run(_COMMANDS[args.cmd](args))
