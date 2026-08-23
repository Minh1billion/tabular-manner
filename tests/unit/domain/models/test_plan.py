import sys
from pathlib import Path

import polars as pl

from tabular_manner.engine.domain.models.plan import Plan

class TestPlanCommit:
    def test_commit_replaces_handle_and_appends_history(self):
        plan = Plan(handle=pl.LazyFrame({"a": [1]}))
        new_handle = pl.LazyFrame({"a": [2]})

        committed = plan.commit(new_handle, step="select")

        assert committed.handle is new_handle
        assert committed.history == ("select",)

    def test_commit_preserves_previous_history(self):
        plan = Plan(handle=pl.LazyFrame({"a": [1]}), history=("fetch",))

        committed = plan.commit(pl.LazyFrame({"a": [2]}), step="select")

        assert committed.history == ("fetch", "select")

    def test_commit_does_not_mutate_original_plan(self):
        original_handle = pl.LazyFrame({"a": [1]})
        plan = Plan(handle=original_handle, history=("fetch",))

        plan.commit(pl.LazyFrame({"a": [2]}), step="select")

        assert plan.handle is original_handle
        assert plan.history == ("fetch",)

    def test_commit_default_step_is_empty_string(self):
        plan = Plan(handle=pl.LazyFrame({"a": [1]}))

        committed = plan.commit(pl.LazyFrame({"a": [2]}))

        assert committed.history == ("",)

class TestPlanWithMeta:
    def test_with_meta_merges_into_existing_meta(self):
        plan = Plan(handle=pl.LazyFrame({"a": [1]}), meta={"execution_id": "e1"})

        updated = plan.with_meta(node_id="n1")

        assert updated.meta == {"execution_id": "e1", "node_id": "n1"}

    def test_with_meta_overwrites_existing_key(self):
        plan = Plan(handle=pl.LazyFrame({"a": [1]}), meta={"execution_id": "e1"})

        updated = plan.with_meta(execution_id="e2")

        assert updated.meta == {"execution_id": "e2"}

    def test_with_meta_does_not_mutate_original_plan(self):
        plan = Plan(handle=pl.LazyFrame({"a": [1]}), meta={"execution_id": "e1"})

        plan.with_meta(node_id="n1")

        assert plan.meta == {"execution_id": "e1"}

    def test_with_meta_preserves_handle_and_history(self):
        handle = pl.LazyFrame({"a": [1]})
        plan = Plan(handle=handle, history=("fetch",))

        updated = plan.with_meta(node_id="n1")

        assert updated.handle is handle
        assert updated.history == ("fetch",)
