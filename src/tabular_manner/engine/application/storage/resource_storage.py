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