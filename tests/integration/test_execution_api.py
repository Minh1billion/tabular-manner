import polars as pl
import pytest

from tabular_manner.engine import build_engine
from tabular_manner.engine.application.io.resource_storage import ResourceStorage
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def engine(tmp_path):
    storage_root = tmp_path / ".resource_storage"
    repository = LocalResourceStorageRepository(root=str(storage_root), namespace=".resource")
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

    def test_schema_error_reports_failing_node_id_and_type(self, engine):
        spec = {
            "nodes": [
                {"id": "1", "type": "fetch_internal", "name": "Fetch", "params": {"key": "raw"}},
                {"id": "2", "type": "select", "name": "Select", "params": {"columns": ["ghost"]}},
            ],
            "connections": [{"from": "1", "to": "2"}],
        }

        events = list(engine.execution.validate(spec))
        failed = next(e for e in events if e["event"] == "failed")

        assert failed["node_id"] == "2"
        assert failed["node_type"] == "select"

    def test_missing_resource_reports_failing_node_id_and_type(self, engine):
        spec = {
            "nodes": [{"id": "1", "type": "fetch_internal", "name": "Fetch", "params": {"key": "missing_key"}}],
            "connections": [],
        }

        events = list(engine.execution.validate(spec))
        failed = next(e for e in events if e["event"] == "failed")

        assert failed["node_id"] == "1"
        assert failed["node_type"] == "fetchinternal"

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

class TestExecuteCancel:
    def test_cancel_before_start_yields_cancelled_event(self, engine):
        events = list(engine.execution.execute(spec=_simple_spec(), cancel_check=lambda: True))

        assert _events_by_name(events) >= {"compiled", "cancelled"}
        assert "completed" not in _events_by_name(events)

    def test_cancel_discards_cached_graph(self, engine):
        events = list(engine.execution.execute(spec=_simple_spec(), cancel_check=lambda: True))
        execution_id = next(e for e in events if e["event"] == "cancelled")["data"]["execution_id"]

        assert execution_id not in engine.execution._graphs

    def test_cancel_mid_traversal_stops_before_completed(self, engine):
        calls = {"n": 0}

        def cancel_after_first_node():
            calls["n"] += 1
            return calls["n"] > 1

        events = list(engine.execution.execute(spec=_simple_spec(), cancel_check=cancel_after_first_node))

        assert "cancelled" in _events_by_name(events)
        assert "completed" not in _events_by_name(events)

    def test_no_cancel_check_runs_to_completion(self, engine):
        events = list(engine.execution.execute(spec=_simple_spec(), cancel_check=lambda: False))

        assert "completed" in _events_by_name(events)

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