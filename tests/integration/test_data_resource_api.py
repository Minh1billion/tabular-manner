import polars as pl
import pytest
from pathlib import Path

from tabular_manner.engine.bootstrap import build_engine

@pytest.fixture
def engine(tmp_path):
    return build_engine(storage_root=str(tmp_path / ".resource_storage"))

def _completed(events: list[dict]) -> dict:
    failed = [e for e in events if e["event"] == "failed"]
    assert not failed, f"unexpected failure: {failed}"
    completed = [e for e in events if e["event"] == "completed"]
    assert completed, "expected a 'completed' event"
    return completed[0]["data"]

def _failed(events: list[dict]) -> dict:
    failed = [e for e in events if e["event"] == "failed"]
    assert failed, "expected a 'failed' event"
    return failed[0]

def _csv_source(tmp_path, name="source.csv") -> dict:
    path = tmp_path / name
    path.write_text("a,b\n1,2\n3,4\n")
    return {"path": str(path)}

class TestImportSource:
    def test_imports_csv_into_storage(self, engine, tmp_path):
        events = list(engine.data_resource.import_source(
            key="raw", source_kind="file", source_params={"path": str(_source_path(tmp_path)), "format": "csv"},
        ))
        data = _completed(events)

        assert data["key"] == "raw"
        assert data["row_count"] == 2
        assert data["columns"] == ["a", "b"]

    def test_rejects_empty_key(self, engine, tmp_path):
        events = list(engine.data_resource.import_source(
            key="   ", source_kind="file", source_params={"path": str(_source_path(tmp_path)), "format": "csv"},
        ))
        error = _failed(events)
        assert "must not be empty" in error["error"]

    def test_rejects_existing_key_without_overwrite(self, engine, tmp_path):
        params = {"path": str(_source_path(tmp_path)), "format": "csv"}
        list(engine.data_resource.import_source(key="raw", source_kind="file", source_params=params))

        events = list(engine.data_resource.import_source(key="raw", source_kind="file", source_params=params))
        error = _failed(events)
        assert "already exists" in error["error"]

    def test_overwrite_replaces_existing_resource(self, engine, tmp_path):
        params = {"path": str(_source_path(tmp_path)), "format": "csv"}
        list(engine.data_resource.import_source(key="raw", source_kind="file", source_params=params))

        events = list(engine.data_resource.import_source(
            key="raw", source_kind="file", source_params=params, overwrite=True,
        ))
        _completed(events)

    def test_rejects_source_with_no_columns(self, engine):
        engine.data_resource._reader_factory.register("empty", _EmptyReaderAdapter)

        events = list(engine.data_resource.import_source(key="raw", source_kind="empty", source_params={}))
        error = _failed(events)
        assert "produced no columns" in error["error"]

class _EmptyReaderAdapter:
    def execute(self) -> pl.LazyFrame:
        return pl.LazyFrame()

def _source_path(tmp_path) -> Path:
    path = tmp_path / "source.csv"
    path.write_text("a,b\n1,2\n3,4\n")
    return path

class TestList:
    def test_lists_saved_keys(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1]}).lazy())
        engine.data_resource._resource_storage.save("cleaned", pl.DataFrame({"a": [1]}).lazy())

        events = list(engine.data_resource.list())
        data = _completed(events)

        assert data["keys"] == ["cleaned", "raw"]

    def test_filters_by_prefix(self, engine):
        engine.data_resource._resource_storage.save("raw_a", pl.DataFrame({"a": [1]}).lazy())
        engine.data_resource._resource_storage.save("cleaned", pl.DataFrame({"a": [1]}).lazy())

        events = list(engine.data_resource.list(prefix="raw"))
        data = _completed(events)

        assert data["keys"] == ["raw_a"]

    def test_respects_limit_and_offset(self, engine):
        for name in ["a", "b", "c"]:
            engine.data_resource._resource_storage.save(name, pl.DataFrame({"x": [1]}).lazy())

        events = list(engine.data_resource.list(limit=1, offset=1))
        data = _completed(events)

        assert data["keys"] == ["b"]

    def test_yields_failed_event_when_bucket_is_invalid(self, engine):
        events = list(engine.data_resource.list(bucket="../escape"))
        error = _failed(events)
        assert "Invalid bucket name" in error["error"]

class TestGet:
    def test_returns_rows_and_schema(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1, 2, 3]}).lazy())

        events = list(engine.data_resource.get("raw"))
        data = _completed(events)

        assert data["row_count"] == 3
        assert data["rows"] == [{"a": 1}, {"a": 2}, {"a": 3}]

    def test_missing_key_fails(self, engine):
        events = list(engine.data_resource.get("does_not_exist"))
        error = _failed(events)
        assert "not found" in error["error"]

    def test_invalid_limit_fails(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1]}).lazy())

        events = list(engine.data_resource.get("raw", limit=0))
        error = _failed(events)
        assert "'limit' must be > 0" in error["error"]

    def test_invalid_offset_fails(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1]}).lazy())

        events = list(engine.data_resource.get("raw", offset=-1))
        error = _failed(events)
        assert "'offset' must be >= 0" in error["error"]

    def test_pagination_with_offset_and_limit(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1, 2, 3, 4]}).lazy())

        events = list(engine.data_resource.get("raw", limit=2, offset=1))
        data = _completed(events)

        assert data["rows"] == [{"a": 2}, {"a": 3}]

class TestExists:
    def test_true_when_present(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1]}).lazy())
        assert engine.data_resource.exists("raw") is True

    def test_false_when_absent(self, engine):
        assert engine.data_resource.exists("ghost") is False

class TestDelete:
    def test_deletes_existing_resource(self, engine):
        engine.data_resource._resource_storage.save("raw", pl.DataFrame({"a": [1]}).lazy())

        events = list(engine.data_resource.delete("raw"))
        data = _completed(events)

        assert data["key"] == "raw"
        assert engine.data_resource.exists("raw") is False

    def test_missing_key_fails(self, engine):
        events = list(engine.data_resource.delete("does_not_exist"))
        error = _failed(events)
        assert "not found" in error["error"]

    def test_rejects_empty_key(self, engine):
        events = list(engine.data_resource.delete("   "))
        error = _failed(events)
        assert "must not be empty" in error["error"]
