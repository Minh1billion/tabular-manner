import polars as pl
import pytest

from tabular_manner.engine.domain.models.schema import Schema

class TestNamesAndGet:
    def test_names_returns_column_names_in_order(self):
        schema = Schema({"a": pl.Int64, "b": pl.String})

        assert schema.names() == ["a", "b"]

    def test_get_returns_dtype_for_existing_column(self):
        schema = Schema({"a": pl.Int64})

        assert schema.get("a") == pl.Int64

    def test_get_returns_none_for_missing_column(self):
        schema = Schema({"a": pl.Int64})

        assert schema.get("ghost") is None

class TestToPolars:
    def test_produces_lazyframe_with_matching_schema_and_zero_rows(self):
        schema = Schema({"a": pl.Int64, "b": pl.String})

        lf = schema.to_polars()

        assert lf.collect_schema() == pl.Schema({"a": pl.Int64, "b": pl.String})
        assert lf.collect().height == 0

class TestAsStrDict:
    def test_converts_dtypes_to_strings(self):
        schema = Schema({"a": pl.Int64, "b": pl.String})

        assert schema.as_str_dict() == {"a": "Int64", "b": "String"}

class TestFromPolars:
    def test_wraps_polars_schema(self):
        polars_schema = pl.LazyFrame({"a": [1], "b": ["x"]}).collect_schema()

        schema = Schema.from_polars(polars_schema)

        assert schema.fields == {"a": pl.Int64, "b": pl.String}

class TestFromDeclared:
    def test_resolves_dtype_names_to_polars_types(self):
        schema = Schema.from_declared({"a": "Int64", "b": "String"})

        assert schema.fields == {"a": pl.Int64, "b": pl.String}

    def test_unknown_dtype_name_raises(self):
        with pytest.raises(ValueError, match="Unknown polars dtype"):
            Schema.from_declared({"a": "NotADtype"})

    def test_non_dtype_attribute_raises(self):
        with pytest.raises(ValueError, match="Unknown polars dtype"):
            Schema.from_declared({"a": "LazyFrame"})