import sys
from pathlib import Path

import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.control import If, Switch
from tabular_manner.engine.domain.models.plan import Plan

class TestSwitchValidation:
    def test_rejects_empty_expression(self):
        with pytest.raises(ValueError, match="'expression' must not be empty"):
            Switch(name="bucket", expression="   ", cases=["high", "low"])

    def test_rejects_empty_cases(self):
        with pytest.raises(ValueError, match="'cases' must not be empty"):
            Switch(name="bucket", expression="df.amount.mean() > 0", cases=[])

    def test_rejects_duplicate_cases(self):
        with pytest.raises(ValueError, match="'cases' must not contain duplicates"):
            Switch(name="bucket", expression="df.amount.mean() > 0", cases=["high", "high"])

    def test_rejects_default_case_colliding_with_cases(self):
        with pytest.raises(ValueError, match="'default_case' must not collide"):
            Switch(
                name="bucket",
                expression="df.amount.mean() > 0",
                cases=["high", "low"],
                default_case="high",
            )

    def test_valid_ports_includes_cases_and_default(self):
        node = Switch(name="bucket", expression="df.amount.mean() > 0", cases=["high", "low"])

        assert node.valid_ports() == ("high", "low", "default")

class TestSwitchEvaluate:
    def test_raises_when_expression_is_not_an_expr(self):
        node = Switch(name="bucket", expression="1 + 1", cases=["high", "low"])
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0]}), meta={"execution_id": "t"})
        with pytest.raises(TypeError, match="must evaluate to a polars Expr"):
            node.forward(plan)

    def test_raises_when_result_has_more_than_one_row(self):
        node = Switch(name="bucket", expression="pl.col('amount')", cases=["high", "low"])
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0, 2.0]}), meta={"execution_id": "t"})
        with pytest.raises(ValueError, match="must reduce to a single scalar value"):
            node.forward(plan)

    def test_falls_back_to_default_case_for_unmatched_value(self):
        node = Switch(
            name="bucket",
            expression="pl.lit('unmatched')",
            cases=["high", "low"],
        )
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0]}), meta={"execution_id": "t"})
        _, port = node.forward(plan)

        assert port == "default"

class TestIfValidation:
    def test_rejects_empty_expression(self):
        with pytest.raises(ValueError, match="'expression' must not be empty"):
            If(name="has_rows", expression="  ")

class TestIfEvaluate:
    def test_raises_when_expression_is_not_an_expr(self):
        node = If(name="has_rows", expression="1 + 1")
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0]}), meta={"execution_id": "t"})
        with pytest.raises(TypeError, match="must evaluate to a polars Expr"):
            node.forward(plan)

    def test_raises_when_result_is_not_boolean(self):
        node = If(name="has_rows", expression="pl.col('amount').sum()")
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0, 2.0]}), meta={"execution_id": "t"})
        with pytest.raises(TypeError, match="must evaluate to a boolean"):
            node.forward(plan)

    def test_aggregates_with_all_when_row_expression_yields_many_rows(self):
        node = If(name="has_rows", expression="pl.col('amount') > 0")
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0, 2.0, 3.0]}), meta={"execution_id": "t"})
        _, port = node.forward(plan)

        assert port == "true"

    def test_false_branch_when_condition_not_met(self):
        node = If(name="has_rows", expression="df.amount.len() > 100")
        node.bind({"material_buffer": _StubMaterialBuffer()})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0]}), meta={"execution_id": "t"})
        _, port = node.forward(plan)

        assert port == "false"

class _StubMaterialBuffer:
    def get_or_materialize(self, key, lf):
        return lf.collect()
