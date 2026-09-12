import pyarrow.parquet as pq
import polars as pl
import pytest

from tabular_manner.engine.application.io.resource_storage import ResourceStorage
from tabular_manner.engine.application.io.writer_factory import WriterFactory
from tabular_manner.engine.application.nodes.builtin.io_bound import PushCsv, PushInternal, PushParquet
from tabular_manner.engine.application.ports.resource_storage_repository import ResourceStorageRepository
from tabular_manner.engine.domain.models.plan import Plan
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)


def _plan(lf: pl.LazyFrame) -> Plan:
    return Plan(handle=lf)


@pytest.fixture
def writer_factory():
    return WriterFactory()


@pytest.fixture
def resource_storage(tmp_path):
    repository = LocalResourceStorageRepository(root=str(tmp_path / ".resource_storage"))
    return ResourceStorage(repository=repository)


class TestPushParquetThreshold:
    def test_small_dataset_uses_fast_path_with_no_progress_events(self, tmp_path, writer_factory):
        node = PushParquet(name="push", path=str(tmp_path / "out.parquet"))  # default threshold 200_000
        node.bind({"writer_factory": writer_factory})

        events = list(node.forward_streaming(_plan(pl.LazyFrame({"a": range(10)}))))

        kinds = [e["kind"] for e in events]
        assert kinds == ["result"]
        assert pq.read_table(tmp_path / "out.parquet").num_rows == 10

    def test_large_dataset_emits_progress_and_writes_all_rows(self, tmp_path, writer_factory):
        node = PushParquet(
            name="push", path=str(tmp_path / "out.parquet"), chunk_rows=1_000, progress_threshold_rows=100
        )
        node.bind({"writer_factory": writer_factory})

        events = list(node.forward_streaming(_plan(pl.LazyFrame({"a": range(5_000)}))))

        progress_events = [e for e in events if e["kind"] == "progress"]
        assert len(progress_events) > 1
        assert progress_events[-1]["processed"] == 5_000
        assert progress_events[-1]["total"] == 5_000
        assert events[-1]["kind"] == "result"
        assert pq.read_table(tmp_path / "out.parquet").num_rows == 5_000

    def test_empty_lazyframe_still_produces_valid_file(self, tmp_path, writer_factory):
        node = PushParquet(
            name="push", path=str(tmp_path / "out.parquet"), chunk_rows=1_000, progress_threshold_rows=0
        )
        node.bind({"writer_factory": writer_factory})

        list(node.forward_streaming(_plan(pl.LazyFrame({"a": pl.Series("a", [], dtype=pl.Int64)}))))

        assert pq.read_table(tmp_path / "out.parquet").num_rows == 0


class TestPushParquetAtomicWrite:
    def test_cancel_mid_stream_leaves_no_partial_file_at_destination(self, tmp_path, writer_factory):
        target = tmp_path / "out.parquet"
        node = PushParquet(
            name="push", path=str(target), chunk_rows=1_000, progress_threshold_rows=100
        )
        node.bind({"writer_factory": writer_factory})

        gen = node.forward_streaming(_plan(pl.LazyFrame({"a": range(5_000)})))
        next(gen)  # first progress tick
        next(gen)  # second progress tick
        gen.close()  # simulate a mid-stream cancel

        assert not target.exists()
        assert not list(tmp_path.glob("*.tmp-*"))

    def test_cancel_mid_stream_does_not_touch_pre_existing_file(self, tmp_path, writer_factory):
        target = tmp_path / "out.parquet"
        # Seed a valid prior export at the same path.
        pl.LazyFrame({"a": [1, 2, 3]}).sink_parquet(str(target))
        original_bytes = target.read_bytes()

        node = PushParquet(
            name="push", path=str(target), chunk_rows=1_000, progress_threshold_rows=100
        )
        node.bind({"writer_factory": writer_factory})

        gen = node.forward_streaming(_plan(pl.LazyFrame({"a": range(5_000)})))
        next(gen)
        gen.close()

        assert target.read_bytes() == original_bytes
        assert not list(tmp_path.glob("*.tmp-*"))

    def test_error_mid_stream_leaves_no_partial_file(self, tmp_path, writer_factory, monkeypatch):
        target = tmp_path / "out.parquet"
        node = PushParquet(
            name="push", path=str(target), chunk_rows=1_000, progress_threshold_rows=100
        )
        node.bind({"writer_factory": writer_factory})

        real_collect_batches = pl.LazyFrame.collect_batches

        def _boom(self, *args, **kwargs):
            for i, batch in enumerate(real_collect_batches(self, *args, **kwargs)):
                if i == 1:
                    raise RuntimeError("boom")
                yield batch

        monkeypatch.setattr(pl.LazyFrame, "collect_batches", _boom)

        with pytest.raises(RuntimeError, match="boom"):
            list(node.forward_streaming(_plan(pl.LazyFrame({"a": range(5_000)}))))

        assert not target.exists()
        assert not list(tmp_path.glob("*.tmp-*"))


class TestPushCsvChunkBoundaries:
    def test_header_written_once_across_multiple_batches(self, tmp_path, writer_factory):
        target = tmp_path / "out.csv"
        node = PushCsv(
            name="push", path=str(target), chunk_rows=1_000, progress_threshold_rows=100
        )
        node.bind({"writer_factory": writer_factory})

        list(node.forward_streaming(_plan(pl.LazyFrame({"a": range(3_500)}))))

        lines = target.read_text().splitlines()
        assert lines[0] == "a"
        assert len(lines) == 3_501  # header + 3500 rows
        result = pl.read_csv(target)
        assert result.height == 3_500


class _NonStreamingRepository(ResourceStorageRepository):
    """Stand-in for a backend (e.g. S3) with no incremental writer."""

    supports_streaming_write = False

    def __init__(self, root):
        self._local = LocalResourceStorageRepository(root=str(root))

    @property
    def storage_options(self):
        return None

    def resolve_write_path(self, key, bucket=None):
        return self._local.resolve_write_path(key, bucket)

    def get_object(self, key, bucket=None):
        return self._local.get_object(key, bucket)

    def list(self, bucket=None):
        return self._local.list(bucket)

    def delete(self, key, bucket=None):
        return self._local.delete(key, bucket)


class TestPushInternalNonStreamingBackend:
    def test_emits_start_and_end_progress_without_incremental_writes(self, tmp_path):
        repository = _NonStreamingRepository(root=tmp_path / ".resource_storage")
        storage = ResourceStorage(repository=repository)
        node = PushInternal(name="push", key="my-resource")
        node.bind({"resource_storage": storage})

        events = list(node.forward_streaming(_plan(pl.LazyFrame({"a": range(10)}))))

        progress_events = [e for e in events if e["kind"] == "progress"]
        assert progress_events == [
            {"kind": "progress", "processed": 0, "total": 10},
            {"kind": "progress", "processed": 10, "total": 10},
        ]
        loaded = storage.load("my-resource")
        assert loaded.collect().height == 10

    def test_cancel_before_blocking_save_starts_is_still_possible(self, tmp_path):
        # Even though we can't cancel *during* the blocking save, the caller
        # can still bail out after seeing the first ("started") progress tick
        # and before the (potentially slow) save has produced anything.
        repository = _NonStreamingRepository(root=tmp_path / ".resource_storage")
        storage = ResourceStorage(repository=repository)
        node = PushInternal(name="push", key="my-resource")
        node.bind({"resource_storage": storage})

        gen = node.forward_streaming(_plan(pl.LazyFrame({"a": range(10)})))
        first = next(gen)
        assert first == {"kind": "progress", "processed": 0, "total": 10}
        gen.close()

        with pytest.raises(KeyError):
            storage.load("my-resource")
