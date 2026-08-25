from pathlib import Path

from ...application.ports.resource_storage_repository import ResourceStorageRepository

class LocalResourceStorageRepository(ResourceStorageRepository):
    def __init__(self, root: str = ".tm", namespace: str = ""):
        self._root = Path(root).resolve()
        self._namespace = namespace.strip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def storage_options(self) -> dict[str, str] | None:
        return None

    def _resolve_bucket_dir(self, bucket: str | None = None) -> Path:
        bucket_name = bucket or "default"
        parts = [bucket_name]
        if self._namespace:
            parts.append(self._namespace)
        candidate = self._root.joinpath(*parts).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"Invalid bucket name '{bucket}'")
        return candidate

    def _resolve_object_path(self, key: str, bucket: str | None = None) -> Path:
        if not key or not key.strip():
            raise ValueError("'key' must not be empty")

        bucket_dir = self._resolve_bucket_dir(bucket)
        candidate = (bucket_dir / key).resolve()
        if bucket_dir not in candidate.parents:
            raise ValueError(f"Invalid key '{key}'")
        return candidate

    def resolve_write_path(self, key: str, bucket: str | None = None) -> str:
        path = self._resolve_object_path(key, bucket)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_object(self, key: str, bucket: str | None = None) -> str:
        path = self._resolve_object_path(key, bucket)
        if not path.exists():
            raise KeyError(f"No resource found under key '{key}'")
        return str(path)

    def list(self, bucket: str | None = None) -> list[str]:
        target_dir = self._resolve_bucket_dir(bucket)
        if not target_dir.exists():
            return []
        return sorted(p.name for p in target_dir.iterdir() if p.is_file())

    def delete(self, key: str, bucket: str | None = None) -> None:
        path = self._resolve_object_path(key, bucket)
        if not path.exists():
            raise KeyError(f"No resource found under key '{key}'")
        path.unlink()
