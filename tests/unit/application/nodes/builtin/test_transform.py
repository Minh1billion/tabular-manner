import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent.parent))

from src.engine.application.nodes.builtin.transform import FillMean, Select
from src.engine.domain.models.plan import Plan

def _plan(data: dict) -> Plan:
    return Plan(handle=pl.LazyFrame(data))

class TestSelect:
    def test_keeps_only_requested_columns(self):
        node = Select(name="sel", columns=["a"])
        plan = _plan({"a": [1, 2], "b": [3, 4]})

        result, port = node.forward(plan)

        assert result.handle.collect_schema().names() == ["a"]
        assert port == "out"

    def test_commits_step_with_node_name(self):
        node = Select(name="sel", columns=["a"])
        plan = _plan({"a": [1], "b": [2]})

        result, _ = node.forward(plan)

        assert result.history == ("sel",)

class TestFillMean:
    def test_fills_nulls_with_column_mean(self):
        node = FillMean(name="fill", columns=["a"])
        plan = _plan({"a": [1.0, None, 3.0]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1.0, 2.0, 3.0]
        assert port == "out"

    def test_only_fills_specified_columns(self):
        node = FillMean(name="fill", columns=["a"])
        plan = _plan({"a": [1.0, None], "b": [None, 5.0]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["b"].to_list() == [None, 5.0]

    def test_commits_step_with_node_name(self):
        node = FillMean(name="fill", columns=["a"])
        plan = _plan({"a": [1.0]})

        result, _ = node.forward(plan)

        assert result.history == ("fill",)
