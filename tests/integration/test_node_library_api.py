import polars as pl
import pytest


from tabular_manner.engine import build_engine
from tabular_manner.engine.application.io.resource_storage import ResourceStorage
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def storage_root(tmp_path):
    root = tmp_path / ".object_storage"
    repository = LocalResourceStorageRepository(root=str(root), namespace=".resource")
    resource_storage = ResourceStorage(repository=repository)
    df = pl.DataFrame({"customer": ["a", "b", "c"], "amount": [10.0, 20.0, 30.0], "quantity": [1, 2, 3]})
    resource_storage.save("raw", df.lazy())
    return root

@pytest.fixture
def node_library_root(storage_root):
    return storage_root / "default" / ".node_lib"

@pytest.fixture
def engine(storage_root):
    return build_engine(storage_root=str(storage_root))

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
        assert "double" in engine.registry_provider.get().keys()
        assert not engine.registry_provider.get().is_builtin("double")

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
        assert "malicious" not in engine.registry_provider.get().keys()

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
        assert "double" not in engine.registry_provider.get().keys()

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

class TestDescribeNodes:
    def test_describes_builtin_operator_metadata(self, engine):
        events = list(engine.node_library.describe_nodes())
        data = _completed(events)

        select = next(d for d in data["builtin"] if d["type"] == "select")
        assert select["required"] == {"columns": "list[str]"}
        assert select["ports_out"] == ["out"]
        assert select["fan_in"] is False
        assert select["in_ports"] is None

    def test_describes_fan_in_operator_metadata(self, engine):
        events = list(engine.node_library.describe_nodes())
        data = _completed(events)

        join = next(d for d in data["builtin"] if d["type"] == "join")
        assert join["fan_in"] is True
        assert join["in_ports"] == ["left", "right"]

    def test_describes_registered_custom_transform(self, engine):
        list(engine.node_library.register_transform(name="double", expression="value * 2"))

        events = list(engine.node_library.describe_nodes())
        data = _completed(events)

        double = next(d for d in data["custom"] if d["type"] == "double")
        assert double["required"] == {"columns": "list[str]"}
        assert not any(d["type"] == "double" for d in data["builtin"])

    def test_unregistered_custom_transform_disappears(self, engine):
        list(engine.node_library.register_transform(name="double", expression="value * 2"))
        list(engine.node_library.unregister_node("double"))

        events = list(engine.node_library.describe_nodes())
        data = _completed(events)

        assert not any(d["type"] == "double" for d in data["custom"])

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

class TestPersistenceAcrossRestart:
    def test_custom_transform_survives_restart(self, storage_root):
        engine_a = build_engine(storage_root=str(storage_root))
        list(engine_a.node_library.register_transform(name="double", expression="value * 2"))
        assert "double" in engine_a.registry_provider.get().keys()

        engine_b = build_engine(storage_root=str(storage_root))
        assert engine_b.registry_provider is not engine_a.registry_provider
        assert "double" in engine_b.registry_provider.get().keys()

        events = list(engine_b.execution.execute(spec=_double_pipeline()))
        data = _completed(events)
        assert data["leaves"][0]["history"] == ["Fetch Data", "Double Amount"]
