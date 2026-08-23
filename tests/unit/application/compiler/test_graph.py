import sys
from pathlib import Path

import polars as pl
import pytest


from tabular_manner.engine.application.compiler.graph import Graph, Node, NodeExecutionError
from tabular_manner.engine.domain.models.operator import Operator
from tabular_manner.engine.domain.models.plan import Plan

class _Passthrough(Operator):
    default_port = "out"

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        return plan.commit(plan.handle, step=self.name), self.default_port

class _Failing(Operator):
    def forward(self, plan: Plan) -> tuple[Plan, str]:
        raise RuntimeError("boom")

class _Concat(Operator):
    fan_in = True
    in_ports = None

    def forward_many(self, plans: list[Plan]) -> tuple[Plan, str]:
        merged_history = ()
        for p in plans:
            merged_history += p.history
        return Plan(handle=plans[0].handle, history=merged_history + (self.name,)), self.default_port

def _initial_plan() -> Plan:
    return Plan(handle=pl.LazyFrame({"a": [1]}), meta={"execution_id": "e1"})

class TestLinearTraversal:
    def test_single_node_is_leaf(self):
        node = Node(id="1", operator=_Passthrough(name="only"))
        graph = Graph({"1": node}, entry_ids=("1",))

        steps = list(graph.traverse(_initial_plan()))

        assert len(steps) == 1
        assert steps[0].node_id == "1"
        assert steps[0].is_leaf

    def test_chain_of_nodes_visited_in_order(self):
        n1 = Node(id="1", operator=_Passthrough(name="a"))
        n2 = Node(id="2", operator=_Passthrough(name="b"))
        n1.out_ports["out"] = ["2"]
        graph = Graph({"1": n1, "2": n2}, entry_ids=("1",))

        steps = list(graph.traverse(_initial_plan()))

        assert [s.node_id for s in steps] == ["1", "2"]
        assert steps[0].is_leaf is False
        assert steps[1].is_leaf is True
        assert steps[1].plan.history == ("a", "b")

class TestFanOut:
    def test_two_branches_both_reached(self):
        n1 = Node(id="1", operator=_Passthrough(name="a"))
        n2 = Node(id="2", operator=_Passthrough(name="b"))
        n3 = Node(id="3", operator=_Passthrough(name="c"))
        n1.out_ports["out"] = ["2", "3"]
        graph = Graph({"1": n1, "2": n2, "3": n3}, entry_ids=("1",))

        steps = list(graph.traverse(_initial_plan()))
        leaf_ids = {s.node_id for s in steps if s.is_leaf}

        assert leaf_ids == {"2", "3"}

class TestFanIn:
    def test_waits_for_all_inputs_before_forwarding(self):
        n1 = Node(id="1", operator=_Passthrough(name="a"))
        n2 = Node(id="2", operator=_Passthrough(name="b"))
        n3 = Node(id="3", operator=_Concat(name="merge"), in_degree=2)
        n1.out_ports["out"] = ["3"]
        n2.out_ports["out"] = ["3"]
        graph = Graph({"1": n1, "2": n2, "3": n3}, entry_ids=("1", "2"))

        steps = list(graph.traverse(_initial_plan()))
        leaves = [s for s in steps if s.is_leaf]

        assert len(leaves) == 1
        assert leaves[0].node_id == "3"
        assert set(leaves[0].plan.history[:-1]) == {"a", "b"}
        assert leaves[0].plan.history[-1] == "merge"

class TestErrorHandling:
    def test_operator_exception_wrapped_in_node_execution_error(self):
        node = Node(id="1", operator=_Failing(name="boom"))
        graph = Graph({"1": node}, entry_ids=("1",))

        with pytest.raises(NodeExecutionError) as exc_info:
            list(graph.traverse(_initial_plan()))

        assert exc_info.value.node_id == "1"
        assert isinstance(exc_info.value.original, RuntimeError)

class TestMaxSteps:
    def test_exceeding_max_steps_raises_runtime_error(self):
        n1 = Node(id="1", operator=_Passthrough(name="a"))
        n2 = Node(id="2", operator=_Passthrough(name="b"))
        n1.out_ports["out"] = ["2"]
        n2.out_ports["out"] = ["1"]
        graph = Graph({"1": n1, "2": n2}, entry_ids=("1",))

        with pytest.raises(RuntimeError, match="exceeded max_steps"):
            list(graph.traverse(_initial_plan(), max_steps=3))

    def test_default_max_steps_based_on_edge_count(self):
        n1 = Node(id="1", operator=_Passthrough(name="a"))
        n2 = Node(id="2", operator=_Passthrough(name="b"))
        n1.out_ports["out"] = ["2"]
        graph = Graph({"1": n1, "2": n2}, entry_ids=("1",))

        assert graph._default_max_steps() == 2
