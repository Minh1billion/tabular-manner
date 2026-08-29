from unittest.mock import patch

import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.io_bound import FetchCsv, FetchPostgres, SinkIO
from tabular_manner.engine.application.io.reader_factory import ReaderFactory
from tabular_manner.engine.domain.models.schema import Schema

@pytest.fixture
def reader_factory():
    return ReaderFactory()

class TestFetchCsvDeclaredSchema:
    def test_declared_schema_skips_file_access(self):
        node = FetchCsv(name="fetch", path="/does/not/exist.csv", schema={"a": "Int64", "b": "String"})

        result = node.infer_schema()

        assert result.fields == {"a": pl.Int64, "b": pl.String}

    def test_no_declared_schema_reads_file_lazily(self, tmp_path, reader_factory):
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,x\n")

        node = FetchCsv(name="fetch", path=str(path))
        node.bind({"reader_factory": reader_factory})

        result = node.infer_schema()

        assert result.fields == {"a": pl.Int64, "b": pl.String}

class TestFetchPostgresSampleSchema:
    def test_declared_schema_skips_query_entirely(self):
        node = FetchPostgres(
            name="fetch", dsn="postgresql://localhost/db", table="customers",
            schema={"id": "Int64"},
        )

        with patch("polars.read_database_uri") as mocked:
            result = node.infer_schema()

        mocked.assert_not_called()
        assert result.fields == {"id": pl.Int64}

    def test_no_declared_schema_samples_with_limit_one(self, reader_factory):
        node = FetchPostgres(name="fetch", dsn="postgresql://localhost/db", table="customers")
        node.bind({"reader_factory": reader_factory})

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            result = node.infer_schema()

        mocked.assert_called_once_with(
            query="SELECT * FROM (SELECT * FROM customers) AS __schema_probe__ LIMIT 1",
            uri="postgresql://localhost/db",
        )
        assert result.fields == {"id": pl.Int64}

class TestSinkIOSchema:
    def test_passes_input_schema_through_unchanged(self):
        class _Sink(SinkIO):
            def _persist(self, lf):
                pass

        node = _Sink(name="sink")
        schema = Schema({"a": pl.Int64})

        assert node.infer_schema(schema) is schema