import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.engine.bootstrap import build_engine
from src.engine.application.storage.resource_storage import ResourceStorage
from src.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def storage_root(tmp_path):
    root = tmp_path / ".resource_storage"
    repository = LocalResourceStorageRepository(root=str(root))
    resource_storage = ResourceStorage(repository=repository)
    df = pl.DataFrame({"customer": ["a", "b", "c"], "amount": [10.0, 20.0, 30.0], "quantity": [1, 2, 3]})
    resource_storage.save("raw", df.lazy())
    return root

@pytest.fixture
def node_library_root(tmp_path):
    return tmp_path / ".node_library"

@pytest.fixture
def engine(storage_root, node_library_root):
    return build_engine(storage_root=str(storage_root), node_library_root=str(node_library_root))

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

def _double_pipeline(node_id: str = "2") -> dict:
    return {
        "name": "Double Amount Pipeline",
        "nodes": [
            {"id": "1", "type": "fetch_internal", "name": "Fetch Data", "params": {"key": "raw"}},
            {"id": node_id, "type": "double", "name": "Double Amount", "params": {"columns": ["amount"]}},
            {"id": "3", "type": "push_internal", "name": "Export Result", "params": {"key": "doubled"}},
        ],
        "connections": [
            {"from": "1", "to": node_id},
            {"from": node_id, "to": "3"},
        ],
    }

class TestRegisterTransform:
    def test_registers_successfully(self, engine):
        events = list(engine.node_library.register_transform(
            name="double", expression="value * 2", description="Doubles a numeric column",
        ))
        data = _completed(events)
        assert data["name"] == "double"
        assert data["expression"] == "value * 2"
        assert "double" in engine.registry.keys()
        assert not engine.registry.is_builtin("double")

    def test_rejects_name_colliding_with_builtin(self, engine):
        events = list(engine.node_library.register_transform(name="select", expression="value * 2"))
        error = _failed(events)
        assert "already registered" in error["error"]

    @pytest.mark.parametrize(
        "expression",
        [
            "pl.read_csv('/etc/passwd')",
            "value.__class__",
            "__import__('os').system('echo hi')",
            "value[0]",
            "(lambda x: x)(value)",
            "[x for x in [1, 2, 3]]",
            "(v := value * 2)",
            "df.amount * 2",
        ],
    )
    def test_rejects_expression_violating_sandbox(self, engine, expression):
        events = list(engine.node_library.register_transform(name="malicious", expression=expression))
        _failed(events)
        assert "malicious" not in engine.registry.keys()

    def test_rejected_expression_is_not_persisted(self, engine, node_library_root):
        list(engine.node_library.register_transform(name="malicious", expression="pl.read_csv('/etc/passwd')"))
        assert not (node_library_root / "malicious.json").exists()

class TestUsingCustomTransformInPipeline:
    def test_pipeline_produces_correct_values(self, engine):
        list(engine.node_library.register_transform(name="double", expression="value * 2"))

        events = list(engine.execution.execute(spec=_double_pipeline()))
        data = _completed(events)
        assert data["leaves"][0]["history"] == ["Fetch Data", "Double Amount"]

        loaded = list(engine.data_resource.get("doubled"))
        rows = _completed(loaded)["rows"]
        amounts = sorted(row["amount"] for row in rows)
        assert amounts == [20.0, 40.0, 60.0]

class TestUnregisterTransform:
    def test_unregister_then_reuse_fails_validation(self, engine):
        list(engine.node_library.register_transform(name="double", expression="value * 2"))

        events = list(engine.node_library.unregister_node("double"))
        _completed(events)
        assert "double" not in engine.registry.keys()

        run_events = list(engine.execution.execute(spec=_double_pipeline()))
        error = _failed(run_events)
        assert "double" in error["error"]

    def test_cannot_unregister_builtin(self, engine):
        events = list(engine.node_library.unregister_node("select"))
        error = _failed(events)
        assert "built-in" in error["error"]

    def test_unregister_unknown_custom_transform_fails(self, engine):
        events = list(engine.node_library.unregister_node("does_not_exist"))
        _failed(events)

class TestGetAndListNodes:
    def test_get_returns_definition(self, engine):
        list(engine.node_library.register_transform(name="double", expression="value * 2", description="x2"))
        events = list(engine.node_library.get_node("double"))
        data = _completed(events)
        assert data["description"] == "x2"

    def test_list_reflects_current_state(self, engine):
        events = list(engine.node_library.list_nodes())
        data = _completed(events)
        assert "select" in data["builtin"]
        assert data["custom"] == []

        list(engine.node_library.register_transform(name="double", expression="value * 2"))
        events = list(engine.node_library.list_nodes())
        data = _completed(events)
        assert [c["name"] for c in data["custom"]] == ["double"]

        list(engine.node_library.unregister_node("double"))
        events = list(engine.node_library.list_nodes())
        data = _completed(events)
        assert data["custom"] == []

def _custom_action_pipeline(node_id: str = "2") -> dict:
    return {
        "name": "Custom Save Action Pipeline",
        "nodes": [
            {"id": "1", "type": "fetch_internal", "name": "Fetch Data", "params": {"key": "raw"}},
            {"id": node_id, "type": "custom_save", "name": "Custom Save", "params": {"key": "custom_export"}},
        ],
        "connections": [
            {"from": "1", "to": node_id},
        ],
    }

class TestRegisterAction:
    def test_registers_successfully(self, engine):
        events = list(engine.node_library.register_action(
            name="custom_save",
            service="resource_storage",
            method="save",
            handle_param="lf",
            description="Saves the current dataframe via resource_storage.save",
        ))
        data = _completed(events)
        assert data["kind"] == "action"
        assert data["service"] == "resource_storage"
        assert data["method"] == "save"
        assert "custom_save" in engine.registry.keys()

    def test_rejects_service_outside_whitelist(self, engine):
        events = list(engine.node_library.register_action(
            name="peek_buffer", service="material_buffer", method="get_or_materialize",
        ))
        error = _failed(events)
        assert "not available" in error["error"]
        assert "peek_buffer" not in engine.registry.keys()

    def test_rejects_method_outside_whitelist(self, engine):
        events = list(engine.node_library.register_action(
            name="wipe_storage", service="resource_storage", method="delete",
        ))
        error = _failed(events)
        assert "not allowed" in error["error"]
        assert "wipe_storage" not in engine.registry.keys()

    def test_rejects_name_colliding_with_builtin(self, engine):
        events = list(engine.node_library.register_action(name="select", service="resource_storage", method="save"))
        error = _failed(events)
        assert "already registered" in error["error"]

class TestUsingCustomActionInPipeline:
    def test_action_persists_data_through_whitelisted_service_call(self, engine):
        list(engine.node_library.register_action(
            name="custom_save", service="resource_storage", method="save", handle_param="lf",
        ))

        events = list(engine.execution.execute(spec=_custom_action_pipeline()))
        _completed(events)

        loaded = list(engine.data_resource.get("custom_export"))
        rows = _completed(loaded)["rows"]
        amounts = sorted(row["amount"] for row in rows)
        assert amounts == [10.0, 20.0, 30.0]

class TestPersistenceAcrossRestart:
    def test_custom_transform_survives_restart(self, storage_root, node_library_root):
        engine_a = build_engine(storage_root=str(storage_root), node_library_root=str(node_library_root))
        list(engine_a.node_library.register_transform(name="double", expression="value * 2"))
        assert "double" in engine_a.registry.keys()

        engine_b = build_engine(storage_root=str(storage_root), node_library_root=str(node_library_root))
        assert engine_b.registry is not engine_a.registry
        assert "double" in engine_b.registry.keys()

        events = list(engine_b.execution.execute(spec=_double_pipeline()))
        data = _completed(events)
        assert data["leaves"][0]["history"] == ["Fetch Data", "Double Amount"]