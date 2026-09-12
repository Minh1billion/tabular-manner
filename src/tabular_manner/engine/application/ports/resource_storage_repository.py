from typing import Any, Iterator, Protocol

import polars as pl

class ResourceStorageRepository(Protocol):
    supports_streaming_write: bool = False

    @property
    def storage_options(self) -> dict[str, str] | None:
        ...

    def resolve_write_path(self, key: str, bucket: str | None = None) -> str:
        ...

    def save_streaming(
        self,
        key: str,
        lf: pl.LazyFrame,
        total: int | None,
        chunk_size: int,
        bucket: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        ...

    def get_object(self, key: str, bucket: str | None = None) -> str:
        ...

    def list(self, bucket: str | None = None) -> list[str]:
        ...

    def delete(self, key: str, bucket: str | None = None) -> None:
        ...