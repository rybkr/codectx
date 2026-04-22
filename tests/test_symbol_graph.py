from __future__ import annotations

from graph.models import RefKind, SymbolKind


def test_build_indexes_python_symbols(symbol_graph):
    assert symbol_graph.has_symbol("helpers")
    assert symbol_graph.has_symbol("helpers.Helper")
    assert symbol_graph.has_symbol("helpers.helper")
    assert symbol_graph.has_symbol("service")
    assert symbol_graph.has_symbol("service.Service")
    assert symbol_graph.has_symbol("service.Service.run")

    assert symbol_graph.symbol_count() == 6

    assert set(symbol_graph.symbols({SymbolKind.MODULE})) == {"helpers", "service"}
    assert set(symbol_graph.symbols({SymbolKind.CLASS})) == {
        "helpers.Helper",
        "service.Service",
    }


def test_build_adds_contains_import_and_call_edges(symbol_graph):
    assert symbol_graph.parent("service.Service") == "service"
    assert symbol_graph.parent("service.Service.run") == "service.Service"
    assert symbol_graph.children("service.Service") == ["service.Service.run"]

    assert "helpers.Helper" in symbol_graph.successors("service", kind=RefKind.IMPORTS)
    assert "helpers.helper" in symbol_graph.successors("service", kind=RefKind.IMPORTS)
    assert symbol_graph.successors("service.Service.run", kind=RefKind.CALLS) == [
        "helpers.helper"
    ]
