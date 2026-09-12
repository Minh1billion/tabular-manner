import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import polars as pl
import pyarrow.parquet as pq

from ..ports.resource_storage_repository import ResourceStorageRepository

class ResourceStorage:
    def __init__(self, repository: ResourceStorageRepository, bucket: str | None = None):
        self._repository = repository
        self._bucket = bucket

    def save(self, key: str, lf: pl.LazyFrame, bucket: str | None = None) -> None:
        path = self._repository.resolve_write_path(
            key=f"{key}.parquet",
            bucket=bucket or self._bucket,
        )
        lf.sink_parquet(path, mkdir=True, storage_options=self._repository.storage_options)

    def save_streaming(
        self,
        key: str,
        lf: pl.LazyFrame,
        bucket: str | None = None,
        chunk_size: int = 100_000,
        estimate_total: bool = True,
        progress_threshold_rows: int | None = 500_000,
    ) -> Iterator[dict[str, Any]]:
        total: int | None = None
        if estimate_total or not getattr(self._repository, "supports_streaming_write", False):
            try:
                total = lf.select(pl.len()).collect().item()
            except Exception:
                total = None

        if not getattr(self._repository, "supports_streaming_write", False):
            if total is not None:
                yield {"processed": 0, "total": total}
            self.save(key, lf, bucket=bucket)
            if total is not None:
                yield {"processed": total, "total": total}
            return

        if total is not None and progress_threshold_rows is not None and total <= progress_threshold_rows:
            self.save(key, lf, bucket=bucket)
            return

        path = self._repository.resolve_write_path(key=f"{key}.parquet", bucket=bucket or self._bucket)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
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
                self.save(key, lf, bucket=bucket)
            else:
                os.replace(tmp_path, path)

    def load(self, key: str, bucket: str | None = None) -> pl.LazyFrame:
        ref = self._repository.get_object(key=f"{key}.parquet", bucket=bucket or self._bucket)
        return pl.scan_parquet(ref, storage_options=self._repository.storage_options)

    def list(self, bucket: str | None = None) -> list[str]:
        entries = self._repository.list(bucket=bucket or self._bucket)
        return sorted(
            name[: -len(".parquet")] for name in entries if name.endswith(".parquet")
        )

    def delete(self, key: str, bucket: str | None = None) -> None:
        self._repository.delete(key=f"{key}.parquet", bucket=bucket or self._bucket)
