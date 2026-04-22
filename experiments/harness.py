from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agents.base_agent import BaseAgent
from agents.beliefs import Belief, BeliefKind, BeliefSource
from detection.context_manager import ContextManager
from detection.invalidation_engine import InvalidationEngine
from graph.dependency_graph import DependencyGraph
from graph.incremental_update import prime_cache

CASES_DIR = Path(__file__).with_name("cases")


@dataclass(frozen=True)
class AgentSeed:
    id: int
    beliefs: tuple[str, ...]


@dataclass(frozen=True)
class EvalScenario:
    name: str
    description: str
    root: Path
    changed_files: tuple[str, ...]
    agents: tuple[AgentSeed, ...]
    expected_impacted: dict[int, tuple[str, ...]]


class EvalAgent(BaseAgent):
    async def run(self) -> None:
        return None


class ExperimentHarness:
    def __init__(self, cases_dir: Path = CASES_DIR):
        self.cases_dir = cases_dir
        self.scenarios = self._load_scenarios()

    async def run(self, scenario_names: list[str] | None = None) -> dict[str, Any]:
        selected = self._select_scenarios(scenario_names)
        results = []
        for scenario in selected:
            results.append(await self._run_scenario(scenario))

        passed = sum(1 for result in results if result["passed"])
        return {
            "scenarios": results,
            "summary": {
                "passed": passed,
                "failed": len(results) - passed,
                "total": len(results),
            },
        }

    def _load_scenarios(self) -> tuple[EvalScenario, ...]:
        scenarios: list[EvalScenario] = []
        for scenario_dir in sorted(
            path for path in self.cases_dir.iterdir() if path.is_dir()
        ):
            manifest = json.loads(
                (scenario_dir / "case.json").read_text(encoding="utf-8")
            )
            scenarios.append(
                EvalScenario(
                    name=manifest["name"],
                    description=manifest["description"],
                    root=scenario_dir,
                    changed_files=tuple(manifest["changed_files"]),
                    agents=tuple(
                        AgentSeed(
                            id=agent_data["id"],
                            beliefs=tuple(agent_data["beliefs"]),
                        )
                        for agent_data in manifest["agents"]
                    ),
                    expected_impacted={
                        int(agent_id): tuple(symbols)
                        for agent_id, symbols in manifest["expected_impacted"].items()
                    },
                )
            )
        return tuple(scenarios)

    def _select_scenarios(self, scenario_names: list[str] | None) -> list[EvalScenario]:
        if not scenario_names:
            return list(self.scenarios)

        by_name = {scenario.name: scenario for scenario in self.scenarios}
        missing = [name for name in scenario_names if name not in by_name]
        if missing:
            raise ValueError(f"unknown scenarios: {', '.join(sorted(missing))}")
        return [by_name[name] for name in scenario_names]

    async def _run_scenario(self, scenario: EvalScenario) -> dict[str, Any]:
        with TemporaryDirectory(prefix="codectx-eval-") as tmpdir:
            root = Path(tmpdir)
            self._write_version(root, scenario, suffix=".before.py")

            prime_cache(root)
            graph = DependencyGraph(root=root)
            await graph.build()

            agents = self._build_agents(scenario.agents)
            context_manager = ContextManager(agents)
            engine = InvalidationEngine(graph=graph, context_manager=context_manager)

            self._write_changed_files(root, scenario)
            impacted = await engine.apply_commit(
                [root / relative_path for relative_path in scenario.changed_files]
            )

            actual = {
                agent.id: tuple(sorted(agent.beliefs.stale_symbols()))
                for agent in agents
            }
            expected = {
                agent_id: tuple(sorted(symbols))
                for agent_id, symbols in scenario.expected_impacted.items()
            }
            normalized_impacted = {
                agent_id: tuple(sorted(symbols))
                for agent_id, symbols in impacted.items()
            }
            inbox_sizes = {agent.id: agent._inbox.qsize() for agent in agents}
            expected_by_agent = {
                agent.id: expected.get(agent.id, ()) for agent in agents
            }

            return {
                "name": scenario.name,
                "description": scenario.description,
                "passed": actual == expected_by_agent,
                "actual_stale_symbols": actual,
                "expected_stale_symbols": expected_by_agent,
                "impacted_by_engine": normalized_impacted,
                "inbox_sizes": inbox_sizes,
            }

    def _write_version(
        self, destination: Path, scenario: EvalScenario, *, suffix: str
    ) -> None:
        for relative_path in self._scenario_python_paths(scenario, suffix):
            source = scenario.root / self._fixture_name(relative_path, suffix)
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def _write_changed_files(self, root: Path, scenario: EvalScenario) -> None:
        for relative_path in scenario.changed_files:
            source = scenario.root / self._fixture_name(relative_path, ".after.py")
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    def _scenario_python_paths(
        self,
        scenario: EvalScenario,
        suffix: str,
    ) -> list[str]:
        suffix_len = len(suffix)
        paths: list[str] = []
        for path in scenario.root.rglob(f"*{suffix}"):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(scenario.root).as_posix()
            paths.append(f"{relative[:-suffix_len]}.py")
        paths.sort()
        return paths

    def _fixture_name(self, relative_path: str, suffix: str) -> str:
        base, ext = relative_path.rsplit(".", 1)
        return f"{base}{suffix}"

    def _build_agents(self, seeds: tuple[AgentSeed, ...]) -> list[EvalAgent]:
        agents: list[EvalAgent] = []
        for seed in seeds:
            agent = EvalAgent(id=seed.id, cfg={})
            for symbol in seed.beliefs:
                agent.beliefs.add(
                    Belief(
                        symbol=symbol,
                        kind=BeliefKind.TASK_DEPENDENCY,
                        value="seeded",
                        source=BeliefSource.TASK,
                    )
                )
            agents.append(agent)
        return agents


def format_report(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


async def run_and_print(scenario_names: list[str] | None = None) -> int:
    report = await ExperimentHarness().run(scenario_names)
    print(format_report(report))
    return 0 if report["summary"]["failed"] == 0 else 1
