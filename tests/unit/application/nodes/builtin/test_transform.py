import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent.parent))

import pytest

from src.engine.application.nodes.builtin.transform import (
    Cast,
    Derive,
    Drop,
    DropDuplicates,
    DropNulls,
    FillMean,
    FillNull,
    Filter,
    Limit,
    Rename,
    Select,
    Sort,
)
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

class TestFillNull:
    def test_fills_nulls_with_given_value(self):
        node = FillNull(name="fill_null", columns=["a"], value=0)
        plan = _plan({"a": [1, None, 3]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 0, 3]
        assert port == "out"

    def test_only_fills_specified_columns(self):
        node = FillNull(name="fill_null", columns=["a"], value="x")
        plan = _plan({"a": [None], "b": [None]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["b"].to_list() == [None]

class TestDropNulls:
    def test_drops_rows_with_null_in_subset(self):
        node = DropNulls(name="dropna", columns=["a"])
        plan = _plan({"a": [1, None, 3], "b": [4, 5, 6]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 3]

    def test_defaults_to_all_columns(self):
        node = DropNulls(name="dropna")
        plan = _plan({"a": [1, 2], "b": [None, 5]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected.height == 1

class TestDropDuplicates:
    def test_removes_duplicate_rows(self):
        node = DropDuplicates(name="dedupe")
        plan = _plan({"a": [1, 1, 2]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert sorted(collected["a"].to_list()) == [1, 2]

    def test_rejects_invalid_keep(self):
        with pytest.raises(ValueError):
            DropDuplicates(name="dedupe", keep="bogus")

class TestRename:
    def test_renames_columns(self):
        node = Rename(name="rn", mapping={"a": "renamed"})
        plan = _plan({"a": [1], "b": [2]})

        result, _ = node.forward(plan)

        assert result.handle.collect_schema().names() == ["renamed", "b"]

    def test_rejects_empty_mapping(self):
        with pytest.raises(ValueError):
            Rename(name="rn", mapping={})

class TestSort:
    def test_sorts_ascending_by_default(self):
        node = Sort(name="sort", by=["a"])
        plan = _plan({"a": [3, 1, 2]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2, 3]

    def test_sorts_descending(self):
        node = Sort(name="sort", by=["a"], descending=True)
        plan = _plan({"a": [3, 1, 2]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [3, 2, 1]

class TestCast:
    def test_casts_column_to_requested_dtype(self):
        node = Cast(name="cast", types={"a": "Float64"})
        plan = _plan({"a": [1, 2, 3]})

        result, _ = node.forward(plan)

        assert result.handle.collect_schema()["a"] == pl.Float64

    def test_rejects_unknown_dtype(self):
        with pytest.raises(ValueError):
            Cast(name="cast", types={"a": "NotADtype"})

    def test_rejects_non_dtype_polars_attribute(self):
        with pytest.raises(ValueError):
            Cast(name="cast", types={"a": "DataFrame"})

class TestDrop:
    def test_removes_specified_columns(self):
        node = Drop(name="drop", columns=["b"])
        plan = _plan({"a": [1], "b": [2]})

        result, port = node.forward(plan)

        assert result.handle.collect_schema().names() == ["a"]
        assert port == "out"

class TestLimit:
    def test_keeps_only_first_n_rows(self):
        node = Limit(name="limit", n=2)
        plan = _plan({"a": [1, 2, 3, 4]})

        result, _ = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2]

    def test_rejects_negative_n(self):
        with pytest.raises(ValueError):
            Limit(name="limit", n=-1)

class TestFilter:
    def test_keeps_rows_matching_expression(self):
        node = Filter(name="filter", expression="df.a >= 2")
        plan = _plan({"a": [1, 2, 3]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["a"].to_list() == [2, 3]
        assert port == "out"

    def test_rejects_empty_expression(self):
        with pytest.raises(ValueError):
            Filter(name="filter", expression="   ")

    def test_rejects_disallowed_expression(self):
        with pytest.raises(ValueError):
            Filter(name="filter", expression="__import__('os')")

    def test_rejects_expression_not_evaluating_to_expr(self):
        node = Filter(name="filter", expression="1 + 1")
        plan = _plan({"a": [1, 2, 3]})

        with pytest.raises(TypeError):
            node.forward(plan)

class TestDerive:
    def test_adds_computed_column(self):
        node = Derive(name="derive", column="doubled", expression="df.a * 2")
        plan = _plan({"a": [1, 2, 3]})

        result, port = node.forward(plan)
        collected = result.handle.collect()

        assert collected["doubled"].to_list() == [2, 4, 6]
        assert port == "out"

    def test_rejects_empty_column(self):
        with pytest.raises(ValueError):
            Derive(name="derive", column="  ", expression="df.a")

    def test_rejects_disallowed_expression(self):
        with pytest.raises(ValueError):
            Derive(name="derive", column="x", expression="df.a.map_elements(pl.read_csv)")