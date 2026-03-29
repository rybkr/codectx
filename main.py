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
    print(f"symbols: {list(graph._symbols)}")


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


async def cmd_context_query(args: argparse.Namespace) -> None:
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


async def cmd_eval_invalidation(args: argparse.Namespace) -> None:
    from experiments.harness import run_and_print

    exit_code = await run_and_print(args.scenarios or None)
    if exit_code:
        raise SystemExit(exit_code)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cv", description="context-validity toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    gb = sub.add_parser("graph:build", help="build dependency graph and print stats")
    gb.add_argument("root", help="path to codebase root")

    gq = sub.add_parser("graph:query", help="query dependents of a symbol")
    gq.add_argument("root", help="path to codebase root")
    gq.add_argument("symbol", help="qualified symbol e.g. mymodule.my_function")

    cq = sub.add_parser(
        "context:query",
        help="query the shared context graph source of truth",
    )
    cq.add_argument("root", help="path to codebase root")
    cq.add_argument("--file", help="repo-relative python file to inspect")
    cq.add_argument("--task", help="task text to rank relevant symbols for")
    cq.add_argument("--symbol", help="symbol to expand into a local context subgraph")
    cq.add_argument("--depth", type=int, default=1, help="subgraph expansion depth for --symbol")
    cq.add_argument("--limit", type=int, default=12, help="max symbols to return for --task")

    ev = sub.add_parser(
        "eval:invalidation",
        help="run reproducible invalidation scenarios",
    )
    ev.add_argument(
        "scenarios",
        nargs="*",
        help="optional scenario names to run",
    )

    rn = sub.add_parser("run", help="run full multi-agent pipeline")
    rn.add_argument("--config", default="config.yaml", help="path to config.yaml")

    return p


_COMMANDS = {
    "context:query": cmd_context_query,
    "eval:invalidation": cmd_eval_invalidation,
    "graph:build": cmd_graph_build,
    "graph:query": cmd_graph_query,
    "run": cmd_run,
}

if __name__ == "__main__":
    args = build_parser().parse_args()
    asyncio.run(_COMMANDS[args.cmd](args))
