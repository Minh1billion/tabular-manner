import sys
from pathlib import Path

import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.merge import Join, Union
from tabular_manner.engine.domain.models.plan import Plan

def _plan(data: dict, history=(), meta=None) -> Plan:
    return Plan(handle=pl.LazyFrame(data), history=history, meta=meta or {})

class TestUnion:
    def test_concatenates_rows_from_both_plans(self):
        node = Union(name="merged")
        left = _plan({"a": [1]}, history=("left",))
        right = _plan({"a": [2]}, history=("right",))

        result, port = node.forward_many([left, right])
        collected = result.handle.collect()

        assert sorted(collected["a"].to_list()) == [1, 2]
        assert port == "out"

    def test_merges_history_and_appends_name(self):
        node = Union(name="merged")
        left = _plan({"a": [1]}, history=("left",))
        right = _plan({"a": [2]}, history=("right",))

        result, _ = node.forward_many([left, right])

        assert result.history == ("left", "right", "merged")

    def test_merges_meta_from_both_plans(self):
        node = Union(name="merged")
        left = _plan({"a": [1]}, meta={"x": 1})
        right = _plan({"a": [2]}, meta={"y": 2})

        result, _ = node.forward_many([left, right])

        assert result.meta == {"x": 1, "y": 2}

    def test_how_relaxed_allows_mismatched_dtypes(self):
        node = Union(name="merged", how="vertical_relaxed")
        left = _plan({"a": [1, 2]})
        right = _plan({"a": [3.0, 4.0]})

        result, _ = node.forward_many([left, right])
        collected = result.handle.collect()

        assert collected.height == 4

class TestJoin:
    def test_joins_on_common_column(self):
        node = Join(name="joined", on=["customer"])
        left = _plan({"customer": ["a", "b"], "amount": [10, 20]})
        right = _plan({"customer": ["a", "b"], "quantity": [1, 2]})

        result, port = node.forward_many([left, right])
        collected = result.handle.collect().sort("customer")

        assert collected["quantity"].to_list() == [1, 2]
        assert port == "out"

    def test_inner_join_drops_unmatched_rows(self):
        node = Join(name="joined", on=["customer"])
        left = _plan({"customer": ["a", "b"], "amount": [10, 20]})
        right = _plan({"customer": ["a"], "quantity": [1]})

        result, _ = node.forward_many([left, right])
        collected = result.handle.collect()

        assert collected.height == 1

    def test_left_join_keeps_unmatched_rows(self):
        node = Join(name="joined", on=["customer"], how="left")
        left = _plan({"customer": ["a", "b"], "amount": [10, 20]})
        right = _plan({"customer": ["a"], "quantity": [1]})

        result, _ = node.forward_many([left, right])
        collected = result.handle.collect()

        assert collected.height == 2

    def test_requires_on_param(self):
        with pytest.raises(ValueError, match="'on' is required"):
            Join(name="joined")
