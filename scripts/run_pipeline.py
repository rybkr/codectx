import argparse
import asyncio
from pathlib import Path


async def run(args: argparse.Namespace) -> None:
    from agents.coding_agent import CodingAgent
    from detection.commit_watcher import CommitWatcher
    from detection.context_manager import ContextManager
    from detection.invalidation_engine import InvalidationEngine
    from experiments.harness import ExperimentHarness
    from graph.dependency_graph import DependencyGraph
    import yaml

    with open(args.config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    graph = DependencyGraph(root=Path(cfg["codebase_root"]))
    await graph.build()
    agents = [
        CodingAgent(id=index, worktree=Path(worktree), graph=graph, cfg=cfg)
        for index, worktree in enumerate(cfg["worktrees"])
    ]
    context_manager = ContextManager(agents=agents)
    engine = InvalidationEngine(graph=graph, context_manager=context_manager)
    watcher = CommitWatcher(worktrees=cfg["worktrees"], engine=engine)
    if cfg.get("mode") == "experiment":
        await ExperimentHarness(agents=agents, watcher=watcher, cfg=cfg).run()
        return
    await asyncio.gather(watcher.watch(), *[agent.run() for agent in agents])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.run_pipeline",
        description="run the full multi-agent pipeline",
    )
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    return parser


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
