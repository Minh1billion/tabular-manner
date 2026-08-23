from unittest.mock import MagicMock

import polars as pl
import pytest

from tabular_manner.engine.api.data_resource import DataResource

@pytest.fixture
def resource_storage():
    return MagicMock()

@pytest.fixture
def reader_factory():
    return MagicMock()

@pytest.fixture
def data_resource(resource_storage, reader_factory):
    return DataResource(resource_storage=resource_storage, reader_factory=reader_factory)

def _events_by_name(events):
    return [e["event"] for e in events]

class TestImportSource:
    def test_yields_completed_event_on_success(self, data_resource, resource_storage, reader_factory):
        resource_storage.list.return_value = []
        reader_factory.read.return_value = pl.LazyFrame({"a": [1, 2]})
        resource_storage.load.return_value = pl.LazyFrame({"a": [1, 2]})

        events = list(data_resource.import_source(key="raw", source_kind="file", source_params={"path": "x.csv"}))

        assert _events_by_name(events)[-1] == "completed"
        completed = events[-1]
        assert completed["data"]["key"] == "raw"
        assert completed["data"]["row_count"] == 2
        resource_storage.save.assert_called_once()

    def test_rejects_empty_key(self, data_resource):
        events = list(data_resource.import_source(key="  ", source_kind="file", source_params={}))

        assert _events_by_name(events) == ["validating", "failed"]

    def test_rejects_existing_key_without_overwrite(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["raw"]

        events = list(data_resource.import_source(key="raw", source_kind="file", source_params={}))

        assert _events_by_name(events) == ["validating", "checking_existing", "failed"]
        assert "already exists" in events[-1]["error"]

    def test_allows_existing_key_with_overwrite(self, data_resource, resource_storage, reader_factory):
        resource_storage.list.return_value = ["raw"]
        reader_factory.read.return_value = pl.LazyFrame({"a": [1]})
        resource_storage.load.return_value = pl.LazyFrame({"a": [1]})

        events = list(
            data_resource.import_source(key="raw", source_kind="file", source_params={}, overwrite=True)
        )

        assert "failed" not in _events_by_name(events)

    def test_rejects_source_with_no_columns(self, data_resource, resource_storage, reader_factory):
        resource_storage.list.return_value = []
        reader_factory.read.return_value = pl.LazyFrame()

        events = list(data_resource.import_source(key="raw", source_kind="file", source_params={}))

        assert _events_by_name(events)[-1] == "failed"
        assert "no columns" in events[-1]["error"]

class TestList:
    def test_yields_completed_event_with_keys(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["a", "b", "c"]

        events = list(data_resource.list())

        assert _events_by_name(events) == ["listing", "completed"]
        assert events[-1]["data"]["keys"] == ["a", "b", "c"]

    def test_filters_by_prefix(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["foo_a", "bar_b", "foo_c"]

        events = list(data_resource.list(prefix="foo_"))

        assert events[-1]["data"]["keys"] == ["foo_a", "foo_c"]

    def test_applies_offset_and_limit(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["a", "b", "c", "d"]

        events = list(data_resource.list(offset=1, limit=2))

        assert events[-1]["data"]["keys"] == ["b", "c"]

    def test_yields_failed_event_when_storage_raises(self, data_resource, resource_storage):
        resource_storage.list.side_effect = RuntimeError("storage unavailable")

        events = list(data_resource.list())

        assert _events_by_name(events) == ["listing", "failed"]
        assert events[-1]["error"] == "storage unavailable"

class TestGet:
    def test_yields_failed_event_when_not_found(self, data_resource, resource_storage):
        resource_storage.list.return_value = []

        events = list(data_resource.get("ghost"))

        assert _events_by_name(events) == ["loading", "failed"]
        assert "not found" in events[-1]["error"]

    def test_rejects_invalid_limit(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["raw"]

        events = list(data_resource.get("raw", limit=0))

        assert _events_by_name(events) == ["loading", "failed"]

    def test_rejects_negative_offset(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["raw"]

        events = list(data_resource.get("raw", offset=-1))

        assert _events_by_name(events) == ["loading", "failed"]

    def test_yields_completed_event_with_rows(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["raw"]
        resource_storage.load.return_value = pl.LazyFrame({"a": [1, 2, 3]})

        events = list(data_resource.get("raw", limit=2, offset=0))

        assert _events_by_name(events) == [
            "loading",
            "schema_loaded",
            "counting_rows",
            "fetching_rows",
            "completed",
        ]
        completed = events[-1]
        assert completed["data"]["row_count"] == 3
        assert completed["data"]["returned_rows"] == 2

class TestDelete:
    def test_rejects_empty_key(self, data_resource):
        events = list(data_resource.delete(""))

        assert _events_by_name(events) == ["validating", "failed"]

    def test_yields_failed_event_when_not_found(self, data_resource, resource_storage):
        resource_storage.list.return_value = []

        events = list(data_resource.delete("ghost"))

        assert _events_by_name(events) == ["validating", "checking_existing", "failed"]

    def test_yields_completed_event_on_success(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["raw"]

        events = list(data_resource.delete("raw"))

        assert _events_by_name(events) == ["validating", "checking_existing", "deleting", "completed"]
        resource_storage.delete.assert_called_once_with("raw", bucket=None)

class TestExists:
    def test_true_when_key_in_storage(self, data_resource, resource_storage):
        resource_storage.list.return_value = ["raw"]

        assert data_resource.exists("raw") is True

    def test_false_when_key_missing(self, data_resource, resource_storage):
        resource_storage.list.return_value = []

        assert data_resource.exists("ghost") is False