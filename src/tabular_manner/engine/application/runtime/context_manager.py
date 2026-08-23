from ..compiler.graph import Node

class ContextManager:
    def __init__(self):
        self._resources: dict[str, object] = {}

    def register(self, name: str, resource: object):
        self._resources[name] = resource
        return self

    def get(self, name: str):
        if name not in self._resources:
            raise ValueError(f"Resource not found: {name}. Availables: {self._resources.keys()}.")
        return self._resources[name]

    def inject(self, nodes: dict[str, Node]) -> None:
        for node in nodes.values():
            node.operator.bind(self._resources)