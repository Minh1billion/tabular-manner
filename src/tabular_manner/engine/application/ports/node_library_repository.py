from typing import Protocol

from ...domain.models.custom_node import CustomNodeDefinition

class NodeLibraryRepository(Protocol):
    def save(self, definition: CustomNodeDefinition, bucket: str | None = None) -> None:
        ...

    def get(self, name: str, bucket: str | None = None) -> CustomNodeDefinition:
        ...

    def delete(self, name: str, bucket: str | None = None) -> None:
        ...

    def list(self, bucket: str | None = None) -> list[CustomNodeDefinition]:
        ...