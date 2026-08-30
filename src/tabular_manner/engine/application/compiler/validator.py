import polars as pl

from ..nodes.registry import NodeRegistry
from ..runtime.sandbox import Sandbox
from .parser import Parser
from .schema_inference import SchemaInference, SchemaInferenceError

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
        self._check_fan_in(spec)
        self._check_ports(spec)
        self._check_no_cycles(spec)
        self._check_schema(spec)

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

    def _check_fan_in(self, spec: dict) -> None:
        incoming: dict[str, list[dict]] = {}
        for c in spec["connections"]:
            incoming.setdefault(c["to"], []).append(c)

        node_types = {n["id"]: n["type"] for n in spec["nodes"]}
        for node_id, conns in incoming.items():
            operator_cls = self.registry.get(node_types[node_id])
            count = len(conns)

            if operator_cls.fan_in:
                if count != 2:
                    raise NodeValidationError(
                        node_id,
                        node_types[node_id],
                        f"Fan-in node '{node_id}' of type '{node_types[node_id]}' must have "
                        f"exactly 2 incoming connections, found {count}",
                    )
                if operator_cls.in_ports is not None:
                    slots = [c.get("into") for c in conns]
                    if sorted(s for s in slots if s is not None) != sorted(operator_cls.in_ports) or len(set(slots)) != len(slots):
                        raise NodeValidationError(
                            node_id,
                            node_types[node_id],
                            f"Fan-in node '{node_id}' of type '{node_types[node_id]}' requires each "
                            f"incoming connection to set 'into' to one of {operator_cls.in_ports} "
                            f"(no duplicates, no missing), got {slots}",
                        )
            elif count > 1:
                raise NodeValidationError(
                    node_id,
                    node_types[node_id],
                    f"Node '{node_id}' of type '{node_types[node_id]}' has multiple incoming "
                    "connections but does not support fan-in",
                )

    def _check_ports(self, spec: dict) -> None:
        for n in spec["nodes"]:
            operator_cls = self.registry.get(n["type"])
            try:
                operator = operator_cls(name=n.get("name"), sandbox=self.sandbox, **n["params"])
            except (ValueError, TypeError) as exc:
                raise NodeValidationError(n["id"], n["type"], f"Invalid params for node '{n['id']}': {exc}") from exc

            valid_ports = operator.valid_ports()
            for c in spec["connections"]:
                if c["from"] != n["id"]:
                    continue
                port = c.get("on", "out")
                if port not in valid_ports:
                    raise NodeValidationError(
                        n["id"],
                        n["type"],
                        f"Connection from node '{n['id']}' uses port '{port}', "
                        f"but valid ports are {valid_ports}",
                    )

    def _check_schema(self, spec: dict) -> None:
        graph = Parser.from_json(spec, self.registry, self.sandbox)
        if self.context_manager is not None:
            self.context_manager.inject(graph.nodes)
        try:
            SchemaInference().infer(graph)
        except SchemaInferenceError as exc:
            if self.context_manager is not None or isinstance(exc.original, pl.exceptions.PolarsError):
                raise
        except Exception:
            if self.context_manager is not None:
                raise

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