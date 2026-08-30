from ..nodes.registry import NodeRegistry
from ..runtime.sandbox import Sandbox
from .graph import Graph, Node

class Parser:
    @classmethod
    def from_json(cls, spec: dict, registry: NodeRegistry, sandbox: Sandbox) -> Graph:
        incoming_counts: dict[str, int] = {}
        for conn in spec["connections"]:
            incoming_counts[conn["to"]] = incoming_counts.get(conn["to"], 0) + 1

        nodes: dict[str, Node] = {}
        for n in spec["nodes"]:
            operator_cls = registry.get(n["type"])
            operator = operator_cls(name=n.get("name"), sandbox=sandbox, **n["params"])
            in_degree = incoming_counts.get(n["id"], 0) or 1
            nodes[n["id"]] = Node(id=n["id"], operator=operator, in_degree=in_degree)

        for conn in spec["connections"]:
            port = conn.get("on", "out")
            nodes[conn["from"]].out_ports.setdefault(port, []).append(conn["to"])

            into = conn.get("into")
            if into is not None:
                nodes[conn["to"]].in_slot_map[into] = conn["from"]

        incoming = {c["to"] for c in spec["connections"]}
        entry_candidates = [n["id"] for n in spec["nodes"] if n["id"] not in incoming]
        if not entry_candidates:
            raise ValueError("Expected at least one entry node, found none")
        entry_ids = tuple(entry_candidates)

        return Graph(nodes, entry_ids)