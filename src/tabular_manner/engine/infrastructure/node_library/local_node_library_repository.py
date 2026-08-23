import json
from dataclasses import asdict
from pathlib import Path

from ...application.ports.node_library_repository import NodeLibraryRepository
from ...domain.models.custom_node import CustomNodeDefinition

class LocalNodeLibraryRepository(NodeLibraryRepository):
    def __init__(self, root: str = ".tm/node_library"):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self._root / f"{name}.json"

    def save(self, definition: CustomNodeDefinition) -> None:
        self._path(definition.name).write_text(json.dumps(asdict(definition), indent=2))

    def get(self, name: str) -> CustomNodeDefinition:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"No custom transform found under name '{name}'")
        return CustomNodeDefinition(**json.loads(path.read_text()))

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"No custom transform found under name '{name}'")
        path.unlink()

    def list(self) -> list[CustomNodeDefinition]:
        return [
            CustomNodeDefinition(**json.loads(path.read_text()))
            for path in sorted(self._root.glob("*.json"))
        ]