from collections import deque

import polars as pl

from ..nodes.registry import NodeRegistry
from ..runtime.sandbox import Sandbox
from .graph import Graph
from .parser import Parser
from .schema_inference import SchemaInferenceError

class NodeValidationError(ValueError):
    def __init__(self, node_id: str, node_type: str, message: str):
        super().__init__(message)
        self.node_id = node_id
        self.node_type = node_type

class Validator:
    def __init__(self, registry: NodeRegistry, sandbox: Sandbox, context_manager=None):
        self.registry = registry
        self.sandbox = sandbox
        self.context_manager = context_manager

    def validate(self, spec: dict) -> None:
        self._check_structure(spec)
        self._check_node_types(spec)
        self._check_connections(spec)
        self._check_has_entry(spec)
        self._check_no_cycles(spec)

        node_types = {n["id"]: n["type"] for n in spec["nodes"]}
        incoming_ids: dict[str, list[str]] = {n["id"]: [] for n in spec["nodes"]}
        for c in spec["connections"]:
            incoming_ids[c["to"]].append(c["from"])

        local_errors = self._collect_local_errors(spec)
        order = self._topological_order(spec)

        blocked: set[str] = set()
        surfaced: list[dict] = []

        for node_id in order:
            if any(parent in blocked or parent in local_errors for parent in incoming_ids[node_id]):
                blocked.add(node_id)
                continue
            if node_id in local_errors:
                surfaced.append({
                    "node_id": node_id,
                    "node_type": node_types[node_id],
                    "message": local_errors[node_id],
                    "exception": NodeValidationError(node_id, node_types[node_id], local_errors[node_id]),
                })
                blocked.add(node_id)

        reduced = {
            "nodes": [n for n in spec["nodes"] if n["id"] not in blocked],
            "connections": [c for c in spec["connections"] if c["from"] not in blocked and c["to"] not in blocked],
        }

        if reduced["nodes"]:
            graph = Parser.from_json(reduced, self.registry, self.sandbox)
            if self.context_manager is not None:
                self.context_manager.inject(graph.nodes)
            surfaced.extend(self._infer_schema_errors(graph))

        if not surfaced:
            return

        errors = [{"node_id": e["node_id"], "node_type": e["node_type"], "message": e["message"]} for e in surfaced]
        exc = surfaced[0]["exception"]
        exc.errors = errors
        raise exc

    def _topological_order(self, spec: dict) -> list[str]:
        in_degree: dict[str, int] = {n["id"]: 0 for n in spec["nodes"]}
        adjacency: dict[str, list[str]] = {n["id"]: [] for n in spec["nodes"]}
        for c in spec["connections"]:
            adjacency[c["from"]].append(c["to"])
            in_degree[c["to"]] += 1

        queue = deque(node_id for node_id, degree in in_degree.items() if degree == 0)
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for next_id in adjacency[node_id]:
                in_degree[next_id] -= 1
                if in_degree[next_id] == 0:
                    queue.append(next_id)
        return order

    def _collect_local_errors(self, spec: dict) -> dict[str, str]:
        node_types = {n["id"]: n["type"] for n in spec["nodes"]}
        errors: dict[str, str] = {}
        operators: dict[str, object] = {}

        for n in spec["nodes"]:
            operator_cls = self.registry.get(n["type"])
            try:
                operators[n["id"]] = operator_cls(name=n.get("name"), sandbox=self.sandbox, **n["params"])
            except (ValueError, TypeError) as exc:
                errors[n["id"]] = f"Invalid params for node '{n['id']}': {exc}"

        incoming: dict[str, list[dict]] = {}
        for c in spec["connections"]:
            incoming.setdefault(c["to"], []).append(c)

        for node_id, conns in incoming.items():
            if node_id in errors:
                continue
            operator_cls = self.registry.get(node_types[node_id])
            count = len(conns)
            if operator_cls.fan_in:
                if count != 2:
                    errors[node_id] = (
                        f"Fan-in node '{node_id}' of type '{node_types[node_id]}' must have "
                        f"exactly 2 incoming connections, found {count}"
                    )
                    continue
                if operator_cls.in_ports is not None:
                    slots = [c.get("into") for c in conns]
                    if sorted(s for s in slots if s is not None) != sorted(operator_cls.in_ports) or len(set(slots)) != len(slots):
                        errors[node_id] = (
                            f"Fan-in node '{node_id}' of type '{node_types[node_id]}' requires each "
                            f"incoming connection to set 'into' to one of {operator_cls.in_ports} "
                            f"(no duplicates, no missing), got {slots}"
                        )
            elif count > 1:
                errors[node_id] = (
                    f"Node '{node_id}' of type '{node_types[node_id]}' has multiple incoming "
                    "connections but does not support fan-in"
                )

        for node_id, operator in operators.items():
            if node_id in errors:
                continue
            valid_ports = operator.valid_ports()
            for c in spec["connections"]:
                if c["from"] != node_id:
                    continue
                port = c.get("on", "out")
                if port not in valid_ports:
                    errors[node_id] = (
                        f"Connection from node '{node_id}' uses port '{port}', "
                        f"but valid ports are {valid_ports}"
                    )
                    break

        return errors

    def _infer_schema_errors(self, graph: Graph) -> list[dict]:
        pending: dict[str, dict[str, object]] = {}
        failed: set[str] = set()
        errors: list[dict] = []
        frontier = deque((entry_id, Graph.ENTRY_SOURCE, None) for entry_id in graph.entry_ids)

        while frontier:
            node_id, source_id, incoming_schema = frontier.popleft()
            if node_id in failed:
                continue
            node = graph.nodes[node_id]
            operator = node.operator

            try:
                if not operator.fan_in:
                    schema = operator.infer_schema() if incoming_schema is None else operator.infer_schema(incoming_schema)
                else:
                    bucket = pending.setdefault(node_id, {})
                    bucket[source_id] = incoming_schema
                    if len(bucket) < node.in_degree:
                        continue
                    if operator.in_ports is not None:
                        ordered = [bucket[node.in_slot_map[slot]] for slot in operator.in_ports]
                    else:
                        ordered = [bucket[key] for key in sorted(bucket)]
                    del pending[node_id]
                    schema = operator.infer_schema_many(ordered)
            except Exception as exc:
                schema_error = SchemaInferenceError(node_id, operator.type, exc)
                failed.add(node_id)
                if self.context_manager is None and not isinstance(exc, pl.exceptions.PolarsError):
                    continue
                errors.append({
                    "node_id": node_id,
                    "node_type": operator.type,
                    "message": str(schema_error),
                    "exception": schema_error,
                })
                continue

            for port, next_ids in node.out_ports.items():
                for next_id in next_ids:
                    frontier.append((next_id, node_id, schema))

        return errors

    def _check_structure(self, spec: dict) -> None:
        if "nodes" not in spec or "connections" not in spec:
            raise ValueError("Spec must contain 'nodes' and 'connections'")

        ids = [n["id"] for n in spec["nodes"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate node ids found")

    def _check_node_types(self, spec: dict) -> None:
        for n in spec["nodes"]:
            if n["type"] not in self.registry.keys():
                raise NodeValidationError(n["id"], n["type"], f"Unknown node type '{n['type']}' for node '{n['id']}'")

    def _check_connections(self, spec: dict) -> None:
        id_set = {n["id"] for n in spec["nodes"]}
        for c in spec["connections"]:
            if c["from"] not in id_set:
                raise ValueError(f"Connection references unknown 'from' id '{c['from']}'")
            if c["to"] not in id_set:
                raise ValueError(f"Connection references unknown 'to' id '{c['to']}'")

    def _check_has_entry(self, spec: dict) -> None:
        incoming = {c["to"] for c in spec["connections"]}
        entry_candidates = [n["id"] for n in spec["nodes"] if n["id"] not in incoming]
        if not entry_candidates:
            raise ValueError("Expected at least one entry node, found none")

    def _check_no_cycles(self, spec: dict) -> None:
        adjacency: dict[str, list[str]] = {n["id"]: [] for n in spec["nodes"]}
        for c in spec["connections"]:
            adjacency[c["from"]].append(c["to"])

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node_id: WHITE for node_id in adjacency}

        for start_id in adjacency:
            if color[start_id] != WHITE:
                continue

            stack: list[tuple[str, list]] = [(start_id, iter(adjacency[start_id]))]
            path = [start_id]
            color[start_id] = GRAY

            while stack:
                node_id, neighbors = stack[-1]
                next_id = next(neighbors, None)

                if next_id is None:
                    color[node_id] = BLACK
                    path.pop()
                    stack.pop()
                    continue

                if color[next_id] == GRAY:
                    cycle = " -> ".join(path[path.index(next_id):] + [next_id])
                    raise ValueError(f"Cycle detected in graph: {cycle}")
                if color[next_id] == WHITE:
                    color[next_id] = GRAY
                    path.append(next_id)
                    stack.append((next_id, iter(adjacency[next_id])))