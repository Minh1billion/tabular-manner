import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.merge import Join, Union
from tabular_manner.engine.domain.models.schema import Schema

class TestUnion:
    def test_infers_combined_schema(self):
        node = Union(name="u")
        left = Schema({"a": pl.Int64, "b": pl.String})
        right = Schema({"a": pl.Int64, "b": pl.String})

        result = node.infer_schema_many([left, right])

        assert result.fields == {"a": pl.Int64, "b": pl.String}

    def test_mismatched_schema_raises_by_default(self):
        node = Union(name="u")
        left = Schema({"a": pl.Int64})
        right = Schema({"a": pl.Int64, "b": pl.String})

        with pytest.raises(pl.exceptions.PolarsError):
            node.infer_schema_many([left, right])

class TestJoin:
    def test_infers_joined_schema(self):
        node = Join(name="j", on=["id"])
        left = Schema({"id": pl.Int64, "x": pl.String})
        right = Schema({"id": pl.Int64, "y": pl.Float64})

        result = node.infer_schema_many([left, right])

        assert result.fields == {"id": pl.Int64, "x": pl.String, "y": pl.Float64}

    def test_missing_join_key_raises(self):
        node = Join(name="j", on=["id"])
        left = Schema({"id": pl.Int64})
        right = Schema({"other": pl.Int64})

        with pytest.raises(pl.exceptions.PolarsError):
            node.infer_schema_many([left, right])