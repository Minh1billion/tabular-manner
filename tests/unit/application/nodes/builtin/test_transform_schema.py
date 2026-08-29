import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.transform import (
    Cast,
    Derive,
    Filter,
    GroupBy,
    Log,
    Rename,
    Select,
)
from tabular_manner.engine.domain.models.schema import Schema

class TestSelect:
    def test_infers_only_selected_columns(self):
        node = Select(name="sel", columns=["a"])
        schema = Schema({"a": pl.Int64, "b": pl.String})

        result = node.infer_schema(schema)

        assert result.names() == ["a"]

    def test_unknown_column_raises(self):
        node = Select(name="sel", columns=["ghost"])
        schema = Schema({"a": pl.Int64})

        with pytest.raises(pl.exceptions.PolarsError):
            node.infer_schema(schema)

class TestRename:
    def test_infers_renamed_column(self):
        node = Rename(name="rn", mapping={"a": "renamed"})
        schema = Schema({"a": pl.Int64, "b": pl.String})

        result = node.infer_schema(schema)

        assert result.names() == ["renamed", "b"]

class TestCast:
    def test_infers_new_dtype(self):
        node = Cast(name="cast", types={"a": "Float64"})
        schema = Schema({"a": pl.Int64})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.Float64

class TestLog:
    def test_keeps_column_name_with_float_dtype(self):
        node = Log(name="log", columns=["a"])
        schema = Schema({"a": pl.Int64})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.Float64

    def test_non_numeric_column_does_not_raise_at_schema_level(self):
        node = Log(name="log", columns=["a"])
        schema = Schema({"a": pl.String})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.Float64

class TestGroupBy:
    def test_infers_group_and_aggregation_dtypes(self):
        node = GroupBy(name="gb", by=["b"], aggregations={"a": "sum"})
        schema = Schema({"a": pl.Int64, "b": pl.String})

        result = node.infer_schema(schema)

        assert result.get("b") == pl.String
        assert result.get("a") == pl.Int64

class TestFilterAndDerive:
    def test_filter_preserves_schema(self):
        node = Filter(name="flt", expression="df.a > 1")
        schema = Schema({"a": pl.Int64})

        result = node.infer_schema(schema)

        assert result.fields == {"a": pl.Int64}

    def test_derive_adds_new_column_with_correct_dtype(self):
        node = Derive(name="dv", column="c", expression="df.a * 2")
        schema = Schema({"a": pl.Int64})

        result = node.infer_schema(schema)

        assert result.get("c") == pl.Int64