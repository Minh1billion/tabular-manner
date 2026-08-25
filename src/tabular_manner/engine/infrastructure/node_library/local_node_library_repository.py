import json
from dataclasses import asdict
from pathlib import Path

from ...application.ports.node_library_repository import NodeLibraryRepository
from ...domain.models.custom_node import CustomNodeDefinition

class LocalNodeLibraryRepository(NodeLibraryRepository):
    def __init__(self, root: str = ".tm", namespace: str = ""):
        self._root = Path(root).resolve()
        self._namespace = namespace.strip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_bucket_dir(self, bucket: str | None = None) -> Path:
        bucket_name = bucket or "default"
        parts = [bucket_name]
        if self._namespace:
            parts.append(self._namespace)
        candidate = self._root.joinpath(*parts).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"Invalid bucket name '{bucket}'")
        return candidate

    def _path(self, name: str, bucket: str | None = None) -> Path:
        if not name or not name.strip():
            raise ValueError("'name' must not be empty")
        bucket_dir = self._resolve_bucket_dir(bucket)
        bucket_dir.mkdir(parents=True, exist_ok=True)
        candidate = (bucket_dir / f"{name}.json").resolve()
        if bucket_dir not in candidate.parents:
            raise ValueError(f"Invalid name '{name}'")
        return candidate

    def save(self, definition: CustomNodeDefinition, bucket: str | None = None) -> None:
        self._path(definition.name, bucket).write_text(json.dumps(asdict(definition), indent=2))

    def get(self, name: str, bucket: str | None = None) -> CustomNodeDefinition:
        path = self._path(name, bucket)
        if not path.exists():
            raise KeyError(f"No custom transform found under name '{name}'")
        return CustomNodeDefinition(**json.loads(path.read_text()))

    def delete(self, name: str, bucket: str | None = None) -> None:
        path = self._path(name, bucket)
        if not path.exists():
            raise KeyError(f"No custom transform found under name '{name}'")
        path.unlink()

    def list(self, bucket: str | None = None) -> list[CustomNodeDefinition]:
        bucket_dir = self._resolve_bucket_dir(bucket)
        if not bucket_dir.exists():
            return []
        return [
            CustomNodeDefinition(**json.loads(path.read_text()))
            for path in sorted(bucket_dir.glob("*.json"))
        ]
