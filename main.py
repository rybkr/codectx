import asyncio
import logging
import yaml
from pathlib import Path

from agents.coding_agent import CodingAgent
from graph.dependency_graph import DependencyGraph
from detection.commit_watcher import CommitWatcher
from detection.invalidation_engine import InvalidationEngine
from detection.context_manager import ContextManager
from experiments.harness import ExperimentHarness

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


async def main():
    cfg = load_config()

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
        harness = ExperimentHarness(agents=agents, watcher=watcher, cfg=cfg)
        await harness.run()
    elif cfg.get("mode") == "live":
        await asyncio.gather(watcher.watch(), *[a.run() for a in agents])


if __name__ == "__main__":
    asyncio.run(main())
