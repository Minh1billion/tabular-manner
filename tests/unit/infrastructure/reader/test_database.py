from unittest.mock import patch

import polars as pl
import pytest

from tabular_manner.engine.infrastructure.reader.database import DatabaseReaderAdapter

class TestInit:
    def test_requires_table_or_query(self):
        with pytest.raises(ValueError, match="Either 'table' or 'query' must be provided"):
            DatabaseReaderAdapter(dsn="postgresql://localhost/db")

    def test_accepts_table_only(self):
        adapter = DatabaseReaderAdapter(dsn="postgresql://localhost/db", table="customers")

        assert adapter.table == "customers"
        assert adapter.query is None

    def test_accepts_query_only(self):
        adapter = DatabaseReaderAdapter(dsn="postgresql://localhost/db", query="SELECT 1")

        assert adapter.query == "SELECT 1"
        assert adapter.table is None

class TestExecute:
    def test_builds_select_all_query_from_table(self):
        adapter = DatabaseReaderAdapter(dsn="postgresql://localhost/db", table="customers")
        expected = pl.DataFrame({"a": [1, 2]})

        with patch("polars.read_database_uri", return_value=expected) as mocked:
            result = adapter.execute()

        mocked.assert_called_once_with(
            query="SELECT * FROM customers", uri="postgresql://localhost/db",
        )
        assert isinstance(result, pl.LazyFrame)
        assert result.collect().to_dict(as_series=False) == {"a": [1, 2]}

    def test_prefers_explicit_query_over_table(self):
        adapter = DatabaseReaderAdapter(
            dsn="postgresql://localhost/db", table="customers", query="SELECT id FROM customers",
        )

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            adapter.execute()

        mocked.assert_called_once_with(
            query="SELECT id FROM customers", uri="postgresql://localhost/db",
        )

    def test_forwards_partition_kwargs_when_set(self):
        adapter = DatabaseReaderAdapter(
            dsn="postgresql://localhost/db",
            table="customers",
            partition_on="id",
            partition_num=4,
        )

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            adapter.execute()

        mocked.assert_called_once_with(
            query="SELECT * FROM customers",
            uri="postgresql://localhost/db",
            partition_on="id",
            partition_num=4,
        )

    def test_omits_partition_kwargs_when_not_set(self):
        adapter = DatabaseReaderAdapter(dsn="postgresql://localhost/db", table="customers")

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            adapter.execute()

        _, kwargs = mocked.call_args
        assert "partition_on" not in kwargs
        assert "partition_num" not in kwargs

class TestSampleSchema:
    def test_wraps_table_query_with_limit_one(self):
        adapter = DatabaseReaderAdapter(dsn="postgresql://localhost/db", table="customers")

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            schema = adapter.sample_schema()

        mocked.assert_called_once_with(
            query="SELECT * FROM (SELECT * FROM customers) AS __schema_probe__ LIMIT 1",
            uri="postgresql://localhost/db",
        )
        assert schema == pl.Schema({"id": pl.Int64})

    def test_wraps_explicit_query_with_limit_one(self):
        adapter = DatabaseReaderAdapter(
            dsn="postgresql://localhost/db", query="SELECT id, name FROM customers WHERE active",
        )

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1], "name": ["x"]})) as mocked:
            adapter.sample_schema()

        mocked.assert_called_once_with(
            query="SELECT * FROM (SELECT id, name FROM customers WHERE active) AS __schema_probe__ LIMIT 1",
            uri="postgresql://localhost/db",
        )

    def test_does_not_forward_partition_kwargs(self):
        adapter = DatabaseReaderAdapter(
            dsn="postgresql://localhost/db", table="customers", partition_on="id", partition_num=4,
        )

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            adapter.sample_schema()

        _, kwargs = mocked.call_args
        assert "partition_on" not in kwargs
        assert "partition_num" not in kwargs