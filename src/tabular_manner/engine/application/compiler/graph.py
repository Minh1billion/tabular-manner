import threading
from collections import deque
from dataclasses import dataclass
from typing import Iterator

from ...domain.models.operator import Operator
from ...domain.models.plan import Plan

_ENTRY_SOURCE = "__entry__"
_DEFAULT_EXECUTION_SCOPE = "__no_execution_id__"

class NodeExecutionError(RuntimeError):
    def __init__(self, node_id: str, node_type: str, original: Exception):
        super().__init__(f"Node '{node_id}' ({node_type}) failed: {original}")
        self.node_id = node_id
        self.node_type = node_type
        self.original = original

@dataclass(frozen=True)
class TraversalStep:
    node_id: str
    plan: Plan
    next_ids: list[str]

    @property
    def is_leaf(self) -> bool:
        return not self.next_ids

class Node:
    def __init__(self, id: str, operator: Operator, in_degree: int = 1):
        self.id = id
        self.operator = operator
        self.in_degree = in_degree
        self.out_ports: dict[str, list[str]] = {}
        self.in_slot_map: dict[str, str] = {}
        self._pending: dict[str, dict[str, Plan]] = {}
        self._pending_lock = threading.Lock()

    def forward(self, source_id: str, plan: Plan) -> tuple[Plan, list[str]] | None:
        if not self.operator.fan_in:
            result_plan, port = self.operator.forward(plan)
            return result_plan, self.out_ports.get(port, [])

        execution_id = plan.meta.get("execution_id", _DEFAULT_EXECUTION_SCOPE)

        with self._pending_lock:
            bucket = self._pending.setdefault(execution_id, {})
            bucket[source_id] = plan
            if len(bucket) < self.in_degree:
                return None

            if self.operator.in_ports is not None:
                ordered_plans = [bucket[self.in_slot_map[slot]] for slot in self.operator.in_ports]
            else:
                ordered_plans = [bucket[key] for key in sorted(bucket)]
            del self._pending[execution_id]

        result_plan, port = self.operator.forward_many(ordered_plans)
        return result_plan, self.out_ports.get(port, [])

class Graph:
    def __init__(self, nodes: dict[str, Node], entry_ids: tuple[str, ...]):
        self.nodes = nodes
        self.entry_ids = entry_ids

    def step(self, node_id: str, source_id: str, plan: Plan) -> tuple[Plan, list[str]] | None:
        node = self.nodes[node_id]
        return node.forward(source_id, plan)

    def _default_max_steps(self) -> int:
        total_edges = sum(len(ids) for node in self.nodes.values() for ids in node.out_ports.values())
        return total_edges + len(self.entry_ids)

    def traverse(self, initial_plan: Plan, max_steps: int | None = None) -> Iterator[TraversalStep]:
        limit = max_steps if max_steps is not None else self._default_max_steps()
        frontier: deque[tuple[str, str, Plan]] = deque(
            (entry_id, _ENTRY_SOURCE, initial_plan) for entry_id in self.entry_ids
        )
        steps = 0

        while frontier:
            if steps >= limit:
                raise RuntimeError(
                    f"Execution exceeded max_steps={limit}; the graph likely contains a cycle "
                    "that bypassed Validator (e.g. built without going through Parser.from_json)."
                )

            node_id, source_id, current_plan = frontier.popleft()
            try:
                result = self.step(node_id, source_id, current_plan)
            except NodeExecutionError:
                raise
            except Exception as exc:
                raise NodeExecutionError(node_id, self.nodes[node_id].operator.type, exc) from exc
            steps += 1

            if result is None:
                continue

            latest, next_ids = result
            yield TraversalStep(node_id=node_id, plan=latest, next_ids=next_ids)

            if next_ids:
                frontier.extend((nid, node_id, latest) for nid in next_ids)