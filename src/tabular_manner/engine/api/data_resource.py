from datetime import datetime, timezone
from typing import Any, Iterator

import polars as pl

from ..application.io.reader_factory import ReaderFactory
from ..application.io.resource_storage import ResourceStorage
from ..application.io.writer_factory import WriterFactory

def _event(name: str, **data: Any) -> dict[str, Any]:
    return {"event": name, "ts": datetime.now(timezone.utc).isoformat(), **data}

class DataResource:
    def __init__(self, resource_storage: ResourceStorage, reader_factory: ReaderFactory, writer_factory: WriterFactory):
        self._resource_storage = resource_storage
        self._reader_factory = reader_factory
        self._writer_factory = writer_factory

    def import_source(self, key: str, source_kind: str, source_params: dict[str, Any], bucket: str | None = None, overwrite: bool = False) -> Iterator[dict[str, Any]]:
        try:
            yield _event("validating", key=key)
            if not key or not key.strip():
                raise ValueError("'key' must not be empty")

            yield _event("checking_existing", key=key, bucket=bucket)
            if self.exists(key, bucket=bucket) and not overwrite:
                raise ValueError(f"Resource '{key}' already exists in bucket '{bucket}'. Pass overwrite=True to replace it.")

            yield _event("reading_source", source_kind=source_kind)
            lf = self._reader_factory.read(source_kind, **source_params)
            schema = lf.collect_schema()
            if not schema.names():
                raise ValueError(f"Source '{source_kind}' produced no columns; nothing to import")
            yield _event("source_read", columns=schema.names())

            yield _event("saving", key=key, bucket=bucket)
            self._resource_storage.save(key, lf, bucket=bucket)
            yield _event("saved", key=key)

            yield _event("counting_rows", key=key)
            row_count = self._resource_storage.load(key, bucket=bucket).select(pl.len()).collect().item()

            yield _event("completed", data={"key": key, "bucket": bucket, "columns": schema.names(), "row_count": row_count})
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def list(self, bucket: str | None = None, prefix: str | None = None, limit: int | None = None, offset: int = 0) -> Iterator[dict[str, Any]]:
        try:
            yield _event("listing", bucket=bucket)
            keys = self._resource_storage.list(bucket=bucket)
            if prefix:
                keys = [key for key in keys if key.startswith(prefix)]
            keys = keys[offset:]
            if limit is not None:
                keys = keys[:limit]
            yield _event("completed", data={"bucket": bucket, "keys": keys})
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def get(self, key: str, bucket: str | None = None, limit: int = 100, offset: int = 0) -> Iterator[dict[str, Any]]:
        try:
            yield _event("loading", key=key, bucket=bucket)
            if not self.exists(key, bucket=bucket):
                raise ValueError(f"Resource '{key}' not found in bucket '{bucket}'")
            if limit < 1 or offset < 0:
                raise ValueError("'limit' must be > 0 and 'offset' must be >= 0")

            lf = self._resource_storage.load(key, bucket=bucket)
            schema = lf.collect_schema()
            yield _event("schema_loaded", schema={name: str(dtype) for name, dtype in schema.items()})

            yield _event("counting_rows")
            total_row_count = lf.select(pl.len()).collect().item()

            yield _event("fetching_rows", offset=offset, limit=limit)
            page = lf.slice(offset, limit).collect(engine="streaming")

            yield _event("completed", data={"key": key, "bucket": bucket, "row_count": total_row_count, "returned_rows": page.height, "offset": offset, "rows": page.to_dicts()})
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def delete(self, key: str, bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            yield _event("validating", key=key)
            if not key or not key.strip():
                raise ValueError("'key' must not be empty")

            yield _event("checking_existing", key=key, bucket=bucket)
            if not self.exists(key, bucket=bucket):
                raise ValueError(f"Resource '{key}' not found in bucket '{bucket}'")

            yield _event("deleting", key=key, bucket=bucket)
            self._resource_storage.delete(key, bucket=bucket)

            yield _event("completed", data={"key": key, "bucket": bucket})
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def export(self, key: str, dest_path: str, format: str = "csv", bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            yield _event("loading", key=key, bucket=bucket)
            if not self.exists(key, bucket=bucket):
                raise ValueError(f"Resource '{key}' not found in bucket '{bucket}'")

            lf = self._resource_storage.load(key, bucket=bucket)

            yield _event("writing", dest_path=dest_path, format=format)
            self._writer_factory.write("file", lf, path=dest_path, format=format)

            yield _event("completed", data={"key": key, "bucket": bucket, "dest_path": dest_path, "format": format})
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def exists(self, key: str, bucket: str | None = None) -> bool:
        return key in self._resource_storage.list(bucket=bucket)