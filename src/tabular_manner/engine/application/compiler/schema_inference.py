from collections import deque

from ...domain.models.schema import Schema
from .graph import Graph

class SchemaInferenceError(RuntimeError):
    def __init__(self, node_id: str, node_type: str, original: Exception):
        super().__init__(f"Node '{node_id}' ({node_type}) failed schema inference: {original}")
        self.node_id = node_id
        self.node_type = node_type
        self.original = original

class SchemaInference:
    def infer(self, graph: Graph) -> dict[str, Schema]:
        schemas: dict[str, Schema] = {}
        pending: dict[str, dict[str, Schema]] = {}
        frontier: deque[tuple[str, str, Schema | None]] = deque(
            (entry_id, Graph.ENTRY_SOURCE, None) for entry_id in graph.entry_ids
        )

        while frontier:
            node_id, source_id, incoming_schema = frontier.popleft()
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
            except SchemaInferenceError:
                raise
            except Exception as exc:
                raise SchemaInferenceError(node_id, operator.type, exc) from exc

            schemas[node_id] = schema
            for port, next_ids in node.out_ports.items():
                for next_id in next_ids:
                    frontier.append((next_id, node_id, schema))

        return schemas