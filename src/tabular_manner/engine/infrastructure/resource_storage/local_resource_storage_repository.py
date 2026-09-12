import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import polars as pl
import pyarrow.parquet as pq

from ...application.ports.resource_storage_repository import ResourceStorageRepository

class LocalResourceStorageRepository(ResourceStorageRepository):
    supports_streaming_write = True

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

    def save_streaming(
        self,
        key: str,
        lf: pl.LazyFrame,
        total: int | None,
        chunk_size: int,
        bucket: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        path = Path(self.resolve_write_path(key, bucket))
        tmp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")

        processed = 0
        writer: pq.ParquetWriter | None = None
        wrote_any_batch = False
        try:
            for batch in lf.collect_batches(chunk_size=chunk_size):
                wrote_any_batch = True
                table = batch.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(str(tmp_path), table.schema)
                writer.write_table(table)
                processed += batch.height
                yield {"processed": processed, "total": total}
        except BaseException:
            if writer is not None:
                writer.close()
            tmp_path.unlink(missing_ok=True)
            raise
        else:
            if writer is not None:
                writer.close()
            if not wrote_any_batch:
                tmp_path.unlink(missing_ok=True)
                lf.sink_parquet(str(path), mkdir=True)
            else:
                os.replace(tmp_path, path)

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
