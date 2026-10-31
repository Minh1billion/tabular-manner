import pytest

from tabular_manner.engine import build_engine
from tabular_manner.engine.application.compiler.validator import Validator
from tabular_manner.engine.application.nodes.registry import NodeRegistry, NodeRegistryProvider
from tabular_manner.engine.application.runtime.sandbox import Sandbox
from tabular_manner.engine.domain.models.schema import Schema

SOURCE_SCHEMA = {"a": "Int64", "b": "String", "c": "Float64"}

def _source(node_id: str, schema: dict[str, str] | None = None) -> dict:
    return {
        "id": node_id,
        "type": "fetch_csv",
        "name": node_id,
        "params": {"path": "x.csv", "schema": schema or SOURCE_SCHEMA},
    }

def _node(node_id: str, node_type: str, params: dict) -> dict:
    return {"id": node_id, "type": node_type, "name": node_id, "params": params}

@pytest.fixture
def validator():
    return Validator(NodeRegistryProvider().get(), Sandbox())

def _names(columns: list[dict]) -> list[str]:
    return [c["name"] for c in columns]

def test_incomplete_node_still_reports_its_inputs(validator):
    spec = {
        "nodes": [_source("1"), _node("2", "select", {})],
        "connections": [{"from": "1", "to": "2"}],
    }
    trace = validator.trace_schemas(spec)
    assert _names(trace["2"]["inputs"]["in"]) == ["a", "b", "c"]
    assert trace["2"]["output"] is None

def test_schema_propagates_through_valid_nodes(validator):
    spec = {
        "nodes": [_source("1"), _node("2", "select", {"columns": ["a", "c"]}), _node("3", "sort", {})],
        "connections": [{"from": "1", "to": "2"}, {"from": "2", "to": "3"}],
    }
    trace = validator.trace_schemas(spec)
    assert _names(trace["1"]["output"]) == ["a", "b", "c"]
    assert _names(trace["3"]["inputs"]["in"]) == ["a", "c"]

def test_dtype_groups_are_reported(validator):
    spec = {"nodes": [_source("1")], "connections": []}
    groups = {c["name"]: c["group"] for c in validator.trace_schemas(spec)["1"]["output"]}
    assert groups == {"a": "numeric", "b": "string", "c": "numeric"}

def test_unknown_column_stops_propagation(validator):
    spec = {
        "nodes": [_source("1"), _node("2", "select", {"columns": ["missing"]}), _node("3", "sort", {})],
        "connections": [{"from": "1", "to": "2"}, {"from": "2", "to": "3"}],
    }
    trace = validator.trace_schemas(spec)
    assert trace["2"]["output"] is None
    assert trace["3"]["inputs"] == {}

def test_join_inputs_are_keyed_by_slot(validator):
    spec = {
        "nodes": [_source("1"), _source("2", {"a": "Int64", "d": "String"}), _node("3", "join", {"on": ["a"]})],
        "connections": [
            {"from": "1", "to": "3", "into": "left"},
            {"from": "2", "to": "3", "into": "right"},
        ],
    }
    trace = validator.trace_schemas(spec)
    assert set(trace["3"]["inputs"]) == {"left", "right"}
    assert _names(trace["3"]["inputs"]["right"]) == ["a", "d"]
    assert _names(trace["3"]["output"]) == ["a", "b", "c", "d"]

def test_join_with_single_input_reports_partial_inputs(validator):
    spec = {
        "nodes": [_source("1"), _node("2", "join", {})],
        "connections": [{"from": "1", "to": "2", "into": "left"}],
    }
    trace = validator.trace_schemas(spec)
    assert set(trace["2"]["inputs"]) == {"left"}
    assert trace["2"]["output"] is None

def test_cycle_is_rejected(validator):
    spec = {
        "nodes": [_node("1", "sort", {}), _node("2", "sort", {})],
        "connections": [{"from": "1", "to": "2"}, {"from": "2", "to": "1"}],
    }
    with pytest.raises(ValueError):
        validator.trace_schemas(spec)

def test_execution_infer_schemas_emits_completed_event(tmp_path):
    engine = build_engine(storage_root=str(tmp_path))
    spec = {"nodes": [_source("1")], "connections": []}
    events = list(engine.execution.infer_schemas(spec))
    assert events[-1]["event"] == "completed"
    assert _names(events[-1]["data"]["nodes"]["1"]["output"]) == ["a", "b", "c"]

def test_execution_infer_schemas_emits_failed_event_for_bad_graph(tmp_path):
    engine = build_engine(storage_root=str(tmp_path))
    spec = {"nodes": [_node("1", "sort", {}), _node("2", "sort", {})], "connections": [{"from": "1", "to": "2"}, {"from": "2", "to": "1"}]}
    events = list(engine.execution.infer_schemas(spec))
    assert events[-1]["event"] == "failed"

@pytest.mark.parametrize("key", sorted(NodeRegistry._builtin_registry.keys()))
def test_param_meta_only_describes_declared_params(key):
    cls = NodeRegistry._builtin_registry[key]
    assert set(cls.param_meta) <= set(cls.required) | set(cls.optional)

def test_describe_nodes_exposes_param_meta(tmp_path):
    engine = build_engine(storage_root=str(tmp_path))
    events = list(engine.node_library.describe_nodes())
    builtin = {d["type"]: d for d in events[-1]["data"]["builtin"]}
    assert builtin["select"]["param_meta"]["columns"]["kind"] == "columns"
    assert builtin["str_case"]["param_meta"]["case"]["options"] == ["upper", "lower", "title"]
    assert builtin["join"]["param_meta"]["on"]["scope"] == "common"

def test_schema_describe_groups_dtypes():
    schema = Schema.from_declared({"i": "Int32", "s": "String", "b": "Boolean", "d": "Date"})
    assert {c["name"]: c["group"] for c in schema.describe()} == {
        "i": "numeric",
        "s": "string",
        "b": "boolean",
        "d": "temporal",
    }
