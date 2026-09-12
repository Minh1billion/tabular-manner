from typing import Any, Iterator

import polars as pl

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

        yield from self._repository.save_streaming(
            key=f"{key}.parquet",
            lf=lf,
            total=total,
            chunk_size=chunk_size,
            bucket=bucket or self._bucket,
        )

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
