import pytest

from tabular_manner.engine.application.compiler.validator import Validator
from tabular_manner.engine.application.nodes.registry import NodeRegistry
from tabular_manner.engine.application.runtime.sandbox import Sandbox

def _spec(nodes, connections):
    return {"nodes": nodes, "connections": connections}

def _node(node_id, node_type="select", params=None):
    return {"id": node_id, "type": node_type, "name": node_id, "params": params or {"columns": ["a"]}}

@pytest.fixture
def validator():
    return Validator(NodeRegistry(), Sandbox())

class TestStructure:
    def test_missing_nodes_key_raises(self, validator):
        with pytest.raises(ValueError, match="'nodes' and 'connections'"):
            validator.validate({"connections": []})

    def test_missing_connections_key_raises(self, validator):
        with pytest.raises(ValueError, match="'nodes' and 'connections'"):
            validator.validate({"nodes": []})

    def test_duplicate_node_ids_raises(self, validator):
        spec = _spec([_node("1"), _node("1")], [])
        with pytest.raises(ValueError, match="Duplicate node ids"):
            validator.validate(spec)

class TestNodeTypes:
    def test_unknown_node_type_raises(self, validator):
        spec = _spec([_node("1", "does_not_exist")], [])
        with pytest.raises(ValueError, match="Unknown node type"):
            validator.validate(spec)

class TestConnections:
    def test_unknown_from_id_raises(self, validator):
        spec = _spec([_node("1", "fetch_internal", {"key": "raw"})], [{"from": "ghost", "to": "1"}])
        with pytest.raises(ValueError, match="unknown 'from' id"):
            validator.validate(spec)

    def test_unknown_to_id_raises(self, validator):
        spec = _spec([_node("1", "fetch_internal", {"key": "raw"})], [{"from": "1", "to": "ghost"}])
        with pytest.raises(ValueError, match="unknown 'to' id"):
            validator.validate(spec)

class TestEntry:
    def test_no_entry_node_raises(self, validator):
        spec = _spec(
            [_node("1"), _node("2")],
            [{"from": "1", "to": "2"}, {"from": "2", "to": "1"}],
        )
        with pytest.raises(ValueError, match="at least one entry node"):
            validator.validate(spec)

class TestFanIn:
    def test_non_fan_in_node_with_multiple_incoming_raises(self, validator):
        spec = _spec(
            [
                _node("1", "fetch_internal", {"key": "raw"}),
                _node("2", "fetch_internal", {"key": "raw"}),
                _node("3", "select"),
            ],
            [{"from": "1", "to": "3"}, {"from": "2", "to": "3"}],
        )
        with pytest.raises(ValueError, match="does not support fan-in"):
            validator.validate(spec)

    def test_fan_in_node_with_wrong_count_raises(self, validator):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2", "union")],
            [{"from": "1", "to": "2"}],
        )
        with pytest.raises(ValueError, match="exactly 2 incoming connections"):
            validator.validate(spec)

    def test_fan_in_node_with_missing_slot_raises(self, validator):
        spec = _spec(
            [
                _node("1", "fetch_internal", {"key": "raw"}),
                _node("2", "fetch_internal", {"key": "raw"}),
                _node("3", "join", {"on": ["customer"]}),
            ],
            [{"from": "1", "to": "3", "into": "left"}, {"from": "2", "to": "3", "into": "left"}],
        )
        with pytest.raises(ValueError, match="requires each"):
            validator.validate(spec)

    def test_fan_in_node_with_valid_slots_passes(self, validator):
        spec = _spec(
            [
                _node("1", "fetch_internal", {"key": "raw"}),
                _node("2", "fetch_internal", {"key": "raw"}),
                _node("3", "join", {"on": ["customer"]}),
            ],
            [{"from": "1", "to": "3", "into": "left"}, {"from": "2", "to": "3", "into": "right"}],
        )
        validator.validate(spec)

class TestPorts:
    def test_invalid_port_raises(self, validator):
        spec = _spec(
            [_node("1", "if", {"expression": "df.a.len() > 0"}), _node("2")],
            [{"from": "1", "to": "2", "on": "maybe"}],
        )
        with pytest.raises(ValueError, match="valid ports are"):
            validator.validate(spec)

    def test_valid_named_port_passes(self, validator):
        spec = _spec(
            [_node("1", "if", {"expression": "df.a.len() > 0"}), _node("2")],
            [{"from": "1", "to": "2", "on": "true"}],
        )
        validator.validate(spec)

    def test_invalid_node_params_raises(self, validator):
        spec = _spec([{"id": "1", "type": "select", "name": "1", "params": {}}], [])
        with pytest.raises(ValueError, match="Invalid params for node"):
            validator.validate(spec)

class TestCycles:
    def test_self_loop_raises(self, validator):
        spec = _spec(
            [_node("0", "fetch_internal", {"key": "raw"}), _node("1", "union", {})],
            [{"from": "0", "to": "1"}, {"from": "1", "to": "1"}],
        )
        with pytest.raises(ValueError, match="Cycle detected"):
            validator.validate(spec)

    def test_indirect_cycle_raises(self, validator):
        spec = _spec(
            [
                _node("0", "fetch_internal", {"key": "raw"}),
                _node("1", "union", {}),
                _node("2"),
                _node("3"),
            ],
            [
                {"from": "0", "to": "1"},
                {"from": "1", "to": "2"},
                {"from": "2", "to": "3"},
                {"from": "3", "to": "1"},
            ],
        )
        with pytest.raises(ValueError, match="Cycle detected"):
            validator.validate(spec)

    def test_valid_dag_passes(self, validator):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2"), _node("3")],
            [{"from": "1", "to": "2"}, {"from": "1", "to": "3"}],
        )
        validator.validate(spec)