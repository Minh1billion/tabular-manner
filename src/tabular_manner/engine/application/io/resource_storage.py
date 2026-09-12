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
    ) -> Iterator[dict[str, Any]]:
        if not getattr(self._repository, "supports_streaming_write", False):
            self.save(key, lf, bucket=bucket)
            return

        path = self._repository.resolve_write_path(key=f"{key}.parquet", bucket=bucket or self._bucket)
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        total: int | None = None
        if estimate_total:
            try:
                total = lf.select(pl.len()).collect().item()
            except Exception:
                total = None

        processed = 0
        writer: pq.ParquetWriter | None = None
        try:
            for batch in lf.collect_batches(chunk_size=chunk_size):
                table = batch.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema)
                writer.write_table(table)
                processed += batch.height
                yield {"processed": processed, "total": total}
        finally:
            if writer is not None:
                writer.close()

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