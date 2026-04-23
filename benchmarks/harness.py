from __future__ import annotations

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from benchmarks.models import (
    BenchmarkAgent,
    BenchmarkCase,
    BenchmarkExpected,
    BenchmarkResult,
)
from context.models import FileUpdate
from context.service import ContextService


CASES_DIR: Path = Path(__file__).with_name("cases")


def load_case(path: Path) -> BenchmarkCase:
    data = json.loads((path / "case.json").read_text("utf-8"))
    return BenchmarkCase(
        name=data["name"],
        root=path,
        agents=tuple(
            BenchmarkAgent(
                name=agent["name"],
                task=agent["task"],
                observes=tuple(agent["observes"]),
            )
            for agent in data["agents"]
        ),
        update_files=tuple(data["update_files"]),
        expected=BenchmarkExpected(
            changed_symbols=tuple(data["expected"]["changed_symbols"]),
            impacted_symbols=tuple(data["expected"]["impacted_symbols"]),
            affected_agents=tuple(data["expected"]["affected_agents"]),
            stale_symbols=tuple(data["expected"]["stale_symbols"]),
        ),
    )


def load_cases(cases_dir: Path = CASES_DIR) -> tuple[BenchmarkCase, ...]:
    return tuple(
        [load_case(path) for path in sorted(cases_dir.iterdir()) if path.is_dir()]
    )


async def run_case(case: BenchmarkCase) -> BenchmarkResult:
    with TemporaryDirectory(prefix="codectx-bench-") as tmp:
        repo = Path(tmp) / "repo"
        shutil.copytree(case.root / "before", repo)

        service = ContextService(repo)
        await service.build()

        sessions = {}
        for agent in case.agents:
            session = service.register_agent(agent.name, agent.task)
            sessions[agent.name] = session
            for symbol in agent.observes:
                service.symbol_details(symbol, agent_id=session.agent_id)

        updates = []
        for relative in case.update_files:
            before_path = case.root / "before" / relative
            after_path = case.root / "after" / relative
            updates.append(
                FileUpdate(
                    path=repo / relative,
                    before=before_path.read_bytes(),
                    after=after_path.read_bytes(),
                )
            )

        report = service.apply_file_updates(updates)

        affected_agents = tuple(agent.name for agent in report.affected_agents)

        stale = []
        for session in report.affected_agents:
            stale_report = service.stale_context(session.agent_id)
            stale.extend(symbol.symbol for symbol in stale_report.stale_symbols)

        actual = BenchmarkResult(
            name=case.name,
            passed=(
                tuple(sorted(report.changed_symbols))
                == tuple(sorted(case.expected.changed_symbols))
                and tuple(sorted(report.impacted_symbols))
                == tuple(sorted(case.expected.impacted_symbols))
                and tuple(sorted(affected_agents))
                == tuple(sorted(case.expected.affected_agents))
                and tuple(sorted(stale)) == tuple(sorted(case.expected.stale_symbols))
            ),
            changed_symbols=tuple(sorted(report.changed_symbols)),
            impacted_symbols=tuple(sorted(report.impacted_symbols)),
            affected_agents=tuple(sorted(affected_agents)),
            stale_symbols=tuple(sorted(stale)),
        )
        return actual
