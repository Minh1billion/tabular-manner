from typing import Protocol

class ResourceStorageRepository(Protocol):
    @property
    def storage_options(self) -> dict[str, str] | None:
        ...

    def resolve_write_path(self, key: str, bucket: str | None = None) -> str:
        ...

    def get_object(self, key: str, bucket: str | None = None) -> str:
        ...

    def list(self, bucket: str | None = None) -> list[str]:
        ...

    def delete(self, key: str, bucket: str | None = None) -> None:
        ...