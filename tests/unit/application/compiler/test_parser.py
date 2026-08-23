import sys
from pathlib import Path

import pytest


from tabular_manner.engine.application.compiler.parser import Parser
from tabular_manner.engine.application.nodes.registry import NodeRegistry
from tabular_manner.engine.application.runtime.sandbox import Sandbox

def _spec(nodes, connections):
    return {"nodes": nodes, "connections": connections}

def _node(node_id, node_type="select", params=None):
    return {"id": node_id, "type": node_type, "name": node_id, "params": params or {"columns": ["a"]}}

@pytest.fixture
def registry():
    return NodeRegistry()

@pytest.fixture
def sandbox():
    return Sandbox()

class TestEntryDetection:
    def test_single_entry_node(self, registry, sandbox):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2")],
            [{"from": "1", "to": "2"}],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.entry_ids == ("1",)

    def test_multiple_entry_nodes(self, registry, sandbox):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2", "fetch_internal", {"key": "raw"})],
            [],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert set(graph.entry_ids) == {"1", "2"}

    def test_no_entry_raises(self, registry, sandbox):
        spec = _spec(
            [_node("1"), _node("2")],
            [{"from": "1", "to": "2"}, {"from": "2", "to": "1"}],
        )
        with pytest.raises(ValueError, match="at least one entry node"):
            Parser.from_json(spec, registry, sandbox)

class TestOutPorts:
    def test_default_port_is_out(self, registry, sandbox):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2")],
            [{"from": "1", "to": "2"}],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["1"].out_ports == {"out": ["2"]}

    def test_named_port_grouped_separately(self, registry, sandbox):
        spec = _spec(
            [
                _node("1", "if", {"expression": "df.a.len() > 0"}),
                _node("2"),
                _node("3"),
            ],
            [{"from": "1", "to": "2", "on": "true"}, {"from": "1", "to": "3", "on": "false"}],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["1"].out_ports == {"true": ["2"], "false": ["3"]}

    def test_fan_out_appends_multiple_targets_to_same_port(self, registry, sandbox):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2"), _node("3")],
            [{"from": "1", "to": "2"}, {"from": "1", "to": "3"}],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["1"].out_ports == {"out": ["2", "3"]}

class TestInSlotMap:
    def test_into_maps_source_to_slot(self, registry, sandbox):
        spec = _spec(
            [
                _node("1", "fetch_internal", {"key": "raw"}),
                _node("2", "fetch_internal", {"key": "raw"}),
                _node("3", "join", {"on": ["customer"]}),
            ],
            [
                {"from": "1", "to": "3", "into": "left"},
                {"from": "2", "to": "3", "into": "right"},
            ],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["3"].in_slot_map == {"left": "1", "right": "2"}

    def test_no_into_leaves_slot_map_empty(self, registry, sandbox):
        spec = _spec(
            [_node("1", "fetch_internal", {"key": "raw"}), _node("2")],
            [{"from": "1", "to": "2"}],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["2"].in_slot_map == {}

class TestInDegree:
    def test_node_with_no_incoming_defaults_to_one(self, registry, sandbox):
        spec = _spec([_node("1", "fetch_internal", {"key": "raw"})], [])
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["1"].in_degree == 1

    def test_node_with_two_incoming_has_in_degree_two(self, registry, sandbox):
        spec = _spec(
            [
                _node("1", "fetch_internal", {"key": "raw"}),
                _node("2", "fetch_internal", {"key": "raw"}),
                _node("3", "union"),
            ],
            [{"from": "1", "to": "3"}, {"from": "2", "to": "3"}],
        )
        graph = Parser.from_json(spec, registry, sandbox)
        assert graph.nodes["3"].in_degree == 2