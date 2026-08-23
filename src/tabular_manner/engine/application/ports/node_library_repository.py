from typing import Protocol

from ...domain.models.custom_node import CustomNodeDefinition

class NodeLibraryRepository(Protocol):
    def save(self, definition: CustomNodeDefinition) -> None:
        ...

    def get(self, name: str) -> CustomNodeDefinition:
        ...

    def delete(self, name: str) -> None:
        ...

    def list(self) -> list[CustomNodeDefinition]:
        ...