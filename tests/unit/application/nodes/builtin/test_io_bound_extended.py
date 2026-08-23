import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from tabular_manner.engine.application.io.reader_factory import ReaderFactory
from tabular_manner.engine.application.io.writer_factory import WriterFactory
from tabular_manner.engine.application.nodes.builtin.io_bound import FetchPostgres, FetchS3, PushPostgres
from tabular_manner.engine.domain.models.plan import Plan

def _empty_plan() -> Plan:
    return Plan(handle=pl.LazyFrame())

class TestFetchS3:
    def test_defaults_to_parquet_and_forwards_region(self):
        node = FetchS3(name="fetch", bucket="my-bucket", key="raw.parquet", region="eu-west-1")

        with patch("polars.scan_parquet", return_value=pl.LazyFrame({"a": [1]})) as mocked:
            result, port = node.forward(_empty_plan())

        mocked.assert_called_once_with(
            "s3://my-bucket/raw.parquet", storage_options={"region": "eu-west-1"},
        )
        assert port == "out"
        assert result.handle.collect().to_dict(as_series=False) == {"a": [1]}

    def test_uses_csv_scan_when_format_is_csv(self):
        node = FetchS3(name="fetch", bucket="my-bucket", key="raw.csv", format="csv")

        with patch("polars.scan_csv", return_value=pl.LazyFrame({"a": [1]})) as mocked:
            node.forward(_empty_plan())

        mocked.assert_called_once_with("s3://my-bucket/raw.csv", storage_options={})

    def test_explicit_storage_options_take_precedence_over_region(self):
        node = FetchS3(
            name="fetch",
            bucket="my-bucket",
            key="raw.parquet",
            region="eu-west-1",
            storage_options={"region": "us-east-1", "aws_access_key_id": "AKIA"},
        )

        with patch("polars.scan_parquet", return_value=pl.LazyFrame()) as mocked:
            node.forward(_empty_plan())

        mocked.assert_called_once_with(
            "s3://my-bucket/raw.parquet",
            storage_options={"region": "us-east-1", "aws_access_key_id": "AKIA"},
        )

class TestFetchPostgres:
    def test_forwards_params_to_database_reader(self):
        reader_factory = ReaderFactory()
        node = FetchPostgres(
            name="fetch",
            dsn="postgresql://localhost/db",
            table="customers",
            partition_on="id",
            partition_num=4,
        )
        node.bind({"reader_factory": reader_factory})

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            result, port = node.forward(_empty_plan())

        mocked.assert_called_once_with(
            query="SELECT * FROM customers",
            uri="postgresql://localhost/db",
            partition_on="id",
            partition_num=4,
        )
        assert port == "out"
        assert result.handle.collect().to_dict(as_series=False) == {"id": [1]}

    def test_uses_query_override_via_shared_factory(self):
        reader_factory = ReaderFactory()
        node = FetchPostgres(
            name="fetch",
            dsn="postgresql://localhost/db",
            table="customers",
            query="SELECT id FROM customers WHERE active",
        )
        node.bind({"reader_factory": reader_factory})

        with patch("polars.read_database_uri", return_value=pl.DataFrame({"id": [1]})) as mocked:
            node.forward(_empty_plan())

        mocked.assert_called_once_with(
            query="SELECT id FROM customers WHERE active", uri="postgresql://localhost/db",
        )

class TestPushPostgres:
    def test_forwards_params_to_database_writer(self):
        writer_factory = WriterFactory()
        node = PushPostgres(
            name="push",
            dsn="postgresql://localhost/db",
            table="customers",
            if_table_exists="replace",
        )
        node.bind({"writer_factory": writer_factory})

        write_mock = MagicMock()
        plan = Plan(handle=pl.LazyFrame({"a": [1]}))
        with patch.object(pl.DataFrame, "write_database", write_mock):
            result, port = node.forward(plan)

        write_mock.assert_called_once_with(
            table_name="customers", connection="postgresql://localhost/db", if_table_exists="replace",
        )
        assert result is plan
        assert port == "out"

    def test_defaults_if_table_exists_to_append(self):
        writer_factory = WriterFactory()
        node = PushPostgres(name="push", dsn="postgresql://localhost/db", table="customers")
        node.bind({"writer_factory": writer_factory})

        write_mock = MagicMock()
        with patch.object(pl.DataFrame, "write_database", write_mock):
            node.forward(Plan(handle=pl.LazyFrame({"a": [1]})))

        _, kwargs = write_mock.call_args
        assert kwargs["if_table_exists"] == "append"
