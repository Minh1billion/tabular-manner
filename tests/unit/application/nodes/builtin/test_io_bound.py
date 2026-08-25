import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.io_bound import (
    FetchArrow,
    FetchCsv,
    FetchInternal,
    FetchParquet,
    PushArrow,
    PushCsv,
    PushInternal,
    PushParquet,
)
from tabular_manner.engine.application.io.reader_factory import ReaderFactory
from tabular_manner.engine.application.io.resource_storage import ResourceStorage
from tabular_manner.engine.application.io.writer_factory import WriterFactory
from tabular_manner.engine.domain.models.plan import Plan
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

def _empty_plan() -> Plan:
    return Plan(handle=pl.LazyFrame())

@pytest.fixture
def reader_factory():
    return ReaderFactory()

@pytest.fixture
def writer_factory():
    return WriterFactory()

@pytest.fixture
def resource_storage(tmp_path):
    repository = LocalResourceStorageRepository(root=str(tmp_path / ".resource_storage"))
    return ResourceStorage(repository=repository)

class TestFetchCsv:
    def test_reads_csv_file(self, tmp_path, reader_factory):
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n3,4\n")

        node = FetchCsv(name="fetch", path=str(path))
        node.bind({"reader_factory": reader_factory})

        result, port = node.forward(_empty_plan())
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 3]
        assert port == "out"


class TestFetchParquet:
    def test_reads_parquet_file(self, tmp_path, reader_factory):
        path = tmp_path / "data.parquet"
        pl.DataFrame({"a": [1, 2]}).write_parquet(path)

        node = FetchParquet(name="fetch", path=str(path))
        node.bind({"reader_factory": reader_factory})

        result, _ = node.forward(_empty_plan())
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2]


class TestFetchArrow:
    def test_reads_arrow_file(self, tmp_path, reader_factory):
        path = tmp_path / "data.arrow"
        pl.DataFrame({"a": [1, 2]}).write_ipc(path)

        node = FetchArrow(name="fetch", path=str(path))
        node.bind({"reader_factory": reader_factory})

        result, _ = node.forward(_empty_plan())
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2]


class TestPushCsv:
    def test_writes_csv_file(self, tmp_path, writer_factory):
        target = tmp_path / "out.csv"
        node = PushCsv(name="push", path=str(target))
        node.bind({"writer_factory": writer_factory})

        plan = Plan(handle=pl.LazyFrame({"a": [1, 2]}))
        result, port = node.forward(plan)

        assert target.exists()
        assert pl.read_csv(target)["a"].to_list() == [1, 2]
        assert result is plan
        assert port == "out"


class TestPushParquet:
    def test_writes_parquet_file(self, tmp_path, writer_factory):
        target = tmp_path / "out.parquet"
        node = PushParquet(name="push", path=str(target))
        node.bind({"writer_factory": writer_factory})

        plan = Plan(handle=pl.LazyFrame({"a": [1, 2]}))
        node.forward(plan)

        assert pl.read_parquet(target)["a"].to_list() == [1, 2]


class TestPushArrow:
    def test_writes_arrow_file(self, tmp_path, writer_factory):
        target = tmp_path / "out.arrow"
        node = PushArrow(name="push", path=str(target))
        node.bind({"writer_factory": writer_factory})

        plan = Plan(handle=pl.LazyFrame({"a": [1, 2]}))
        node.forward(plan)

        assert pl.read_ipc(target)["a"].to_list() == [1, 2]


class TestFetchInternal:
    def test_reads_saved_resource(self, resource_storage):
        resource_storage.save("raw", pl.DataFrame({"a": [1, 2]}).lazy())

        node = FetchInternal(name="fetch", key="raw")
        node.bind({"resource_storage": resource_storage})

        result, _ = node.forward(_empty_plan())
        collected = result.handle.collect()

        assert collected["a"].to_list() == [1, 2]


class TestPushInternal:
    def test_saves_resource(self, resource_storage):
        node = PushInternal(name="push", key="processed")
        node.bind({"resource_storage": resource_storage})

        plan = Plan(handle=pl.LazyFrame({"a": [1, 2]}))
        node.forward(plan)

        assert resource_storage.list() == ["processed"]
