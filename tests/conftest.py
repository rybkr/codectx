from __future__ import annotations

import asyncio

import pytest

from graph.symbol_graph import SymbolGraph


@pytest.fixture
def symbol_graph(tmp_path):
    (tmp_path / "helpers.py").write_text(
        """
class Helper:
    pass


def helper() -> Helper:
    return Helper()
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "service.py").write_text(
        """
from helpers import Helper, helper


class Service:
    def run(self) -> Helper:
        return helper()
""".lstrip(),
        encoding="utf-8",
    )

    graph = SymbolGraph(root=tmp_path)
    asyncio.run(graph.build())
    return graph
