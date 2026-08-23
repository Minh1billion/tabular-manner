import polars as pl
import pytest

from tabular_manner.engine.bootstrap import build_engine
from tabular_manner.engine.application.storage.resource_storage import ResourceStorage
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def engine(tmp_path):
    storage_root = tmp_path / ".resource_storage"
    repository = LocalResourceStorageRepository(root=str(storage_root))
    resource_storage = ResourceStorage(repository=repository)
    resource_storage.save("raw", pl.DataFrame({"customer": ["a", "b"], "amount": [10.0, 20.0]}).lazy())
    return build_engine(storage_root=str(storage_root))

def _simple_spec() -> dict:
    return {
        "nodes": [
            {"id": "1", "type": "fetch_internal", "name": "Fetch", "params": {"key": "raw"}},
            {"id": "2", "type": "select", "name": "Select", "params": {"columns": ["customer"]}},
        ],
        "connections": [{"from": "1", "to": "2"}],
    }

def _events_by_name(events):
    return {e["event"] for e in events}

class TestValidate:
    def test_valid_spec_yields_valid_event(self, engine):
        events = list(engine.execution.validate(_simple_spec()))

        assert _events_by_name(events) == {"validating", "valid"}

    def test_invalid_spec_yields_failed_event(self, engine):
        events = list(engine.execution.validate({"nodes": [], "connections": []}))

        assert "failed" in _events_by_name(events)

    def test_does_not_populate_graphs_cache(self, engine):
        list(engine.execution.validate(_simple_spec()))

        assert engine.execution._graphs == {}

class TestCompile:
    def test_compile_yields_compiled_event(self, engine):
        events = list(engine.execution._compile(_simple_spec()))

        assert "compiled" in _events_by_name(events)
        compiled = next(e for e in events if e["event"] == "compiled")
        assert compiled["data"]["entries"] == ["1"]
        assert compiled["data"]["node_count"] == 2

    def test_compile_invalid_spec_yields_failed_event(self, engine):
        events = list(engine.execution._compile({"nodes": [], "connections": []}))

        assert "failed" in _events_by_name(events)

class TestExecuteWithSpec:
    def test_execute_with_spec_compiles_and_runs(self, engine):
        events = list(engine.execution.execute(spec=_simple_spec()))

        completed = next(e for e in events if e["event"] == "completed")
        assert len(completed["data"]["leaves"]) == 1

class TestExecuteWithExecutionId:
    def test_reuses_compiled_graph(self, engine):
        first_run = list(engine.execution.execute(spec=_simple_spec()))
        execution_id = next(e for e in first_run if e["event"] == "compiled")["data"]["execution_id"]

        events = list(engine.execution.execute(execution_id=execution_id))
        completed = next(e for e in events if e["event"] == "completed")

        assert completed["data"]["execution_id"] == execution_id

    def test_unknown_execution_id_raises_failed_event(self, engine):
        events = list(engine.execution.execute(execution_id="does-not-exist"))

        error = next(e for e in events if e["event"] == "failed")
        assert "Unknown execution_id" in error["error"]

    def test_neither_execution_id_nor_spec_raises_failed_event(self, engine):
        events = list(engine.execution.execute())

        error = next(e for e in events if e["event"] == "failed")
        assert "Either" in error["error"]

class TestExecuteFailure:
    def test_node_failure_reports_node_id_and_type(self, engine):
        spec = {
            "nodes": [{"id": "1", "type": "fetch_internal", "name": "Fetch", "params": {"key": "missing_key"}}],
            "connections": [],
        }

        events = list(engine.execution.execute(spec=spec))
        error = next(e for e in events if e["event"] == "failed")

        assert error["node_id"] == "1"
        assert error["node_type"] == "fetchinternal"