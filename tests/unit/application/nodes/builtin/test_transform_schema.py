import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.transform import (
    Bin,
    Cast,
    DatePart,
    Derive,
    ExtractRegex,
    Filter,
    GroupBy,
    Log,
    MapValues,
    ParseDate,
    Rename,
    Round,
    Select,
    Transform,
    Unpivot,
)
from tabular_manner.engine.domain.models.operator import SchemaStrategy
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

class TestRound:
    def test_preserves_float_dtype(self):
        node = Round(name="round", columns=["a"], decimals=1)
        schema = Schema({"a": pl.Float64})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.Float64

class TestBin:
    def test_adds_categorical_bin_column(self):
        node = Bin(name="bin", column="a", breaks=[10.0, 20.0])
        schema = Schema({"a": pl.Int64})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.Int64
        assert result.get("a_bin") is not None

class TestExtractRegex:
    def test_adds_extracted_string_column(self):
        node = ExtractRegex(name="extract", column="s", pattern=r"id-(\d+)")
        schema = Schema({"s": pl.String})

        result = node.infer_schema(schema)

        assert result.get("s_extracted") == pl.String

class TestParseDate:
    def test_infers_date_dtype(self):
        node = ParseDate(name="parse", columns=["d"], format="%Y-%m-%d")
        schema = Schema({"d": pl.String})

        result = node.infer_schema(schema)

        assert result.get("d") == pl.Date

class TestDatePart:
    def test_adds_integer_part_column(self):
        node = DatePart(name="part", column="d", part="year")
        schema = Schema({"d": pl.Date})

        result = node.infer_schema(schema)

        assert result.get("d_year") == pl.Int32

class TestUnpivot:
    def test_infers_variable_value_columns(self):
        node = Unpivot(name="unpivot", index=["id"])
        schema = Schema({"id": pl.Int64, "x": pl.Int64, "y": pl.Int64})

        result = node.infer_schema(schema)

        assert result.names() == ["id", "variable", "value"]
        assert result.get("value") == pl.Int64

class TestMapValues:
    def test_preserves_column_dtype(self):
        node = MapValues(name="map", column="a", mapping={"x": "X"})
        schema = Schema({"a": pl.String})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.String

class TestSchemaStrategyDispatch:
    def test_structural_strategy_uses_apply(self):
        node = Round(name="round", columns=["a"], decimals=1)
        schema = Schema({"a": pl.Float64})

        assert node.schema_strategy is SchemaStrategy.STRUCTURAL
        result = node.infer_schema(schema)

        assert result.get("a") == pl.Float64

    def test_declared_strategy_uses_declared_schema_instead_of_apply(self):
        class _DeclaredDouble(Transform):
            schema_strategy = SchemaStrategy.DECLARED
            required = {"columns": (list, str)}

            def _apply(self, lf):
                raise AssertionError("_apply must not be called for DECLARED strategy")

            def declared_schema(self, input_schema):
                return Schema({**input_schema.fields, "extra": pl.String})

        node = _DeclaredDouble(name="declared", columns=["a"])
        schema = Schema({"a": pl.Int64})

        result = node.infer_schema(schema)

        assert result.get("a") == pl.Int64
        assert result.get("extra") == pl.String