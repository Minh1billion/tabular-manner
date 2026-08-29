import pytest

from tabular_manner.engine.application.compiler.parser import Parser
from tabular_manner.engine.application.compiler.schema_inference import SchemaInference, SchemaInferenceError
from tabular_manner.engine.application.nodes.registry import NodeRegistry
from tabular_manner.engine.application.runtime.sandbox import Sandbox

def _node(node_id, node_type, params):
    return {"id": node_id, "type": node_type, "name": node_id, "params": params}

def _graph(nodes, connections):
    spec = {"nodes": nodes, "connections": connections}
    return Parser.from_json(spec, NodeRegistry(), Sandbox())

class TestLinearChain:
    def test_propagates_schema_through_single_input_nodes(self):
        graph = _graph(
            [
                _node("src", "fetch_csv", {"path": "x.csv", "schema": {"a": "Int64", "b": "String"}}),
                _node("log", "log", {"columns": ["a"]}),
                _node("sel", "select", {"columns": ["a"]}),
            ],
            [{"from": "src", "to": "log"}, {"from": "log", "to": "sel"}],
        )

        schemas = SchemaInference().infer(graph)

        assert schemas["src"].names() == ["a", "b"]
        assert schemas["log"].get("a").is_float()
        assert schemas["sel"].names() == ["a"]

class TestFanIn:
    def test_waits_for_both_branches_before_inferring(self):
        graph = _graph(
            [
                _node("l", "fetch_csv", {"path": "l.csv", "schema": {"id": "Int64", "x": "String"}}),
                _node("r", "fetch_csv", {"path": "r.csv", "schema": {"id": "Int64", "y": "Float64"}}),
                _node("j", "join", {"on": ["id"]}),
            ],
            [
                {"from": "l", "to": "j", "into": "left"},
                {"from": "r", "to": "j", "into": "right"},
            ],
        )

        schemas = SchemaInference().infer(graph)

        assert schemas["j"].names() == ["id", "x", "y"]

class TestErrorReporting:
    def test_raises_with_failing_node_id_and_type(self):
        graph = _graph(
            [
                _node("src", "fetch_csv", {"path": "x.csv", "schema": {"a": "Int64"}}),
                _node("sel", "select", {"columns": ["ghost"]}),
            ],
            [{"from": "src", "to": "sel"}],
        )

        with pytest.raises(SchemaInferenceError) as excinfo:
            SchemaInference().infer(graph)

        assert excinfo.value.node_id == "sel"
        assert excinfo.value.node_type == "select"

    def test_error_on_first_node_does_not_reach_downstream(self):
        graph = _graph(
            [
                _node("src", "fetch_csv", {"path": "x.csv", "schema": {"a": "Int64"}}),
                _node("bad", "cast", {"types": {"ghost": "Float64"}}),
                _node("after", "select", {"columns": ["a"]}),
            ],
            [{"from": "src", "to": "bad"}, {"from": "bad", "to": "after"}],
        )

        with pytest.raises(SchemaInferenceError) as excinfo:
            SchemaInference().infer(graph)

        assert excinfo.value.node_id == "bad"