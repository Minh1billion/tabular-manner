import polars as pl

from ..ports.writer_adapter import WriterAdapter

class WriterFactory:
    def __init__(self, adapters: dict[str, type[WriterAdapter]] | None = None):
        self._adapters: dict[str, type[WriterAdapter]] = dict(self._default_adapters())
        if adapters:
            self._adapters.update(adapters)

    @staticmethod
    def _default_adapters() -> dict[str, type[WriterAdapter]]:
        from ...infrastructure.writer.database import DatabaseWriterAdapter
        from ...infrastructure.writer.file import FileWriterAdapter

        return {
            "file": FileWriterAdapter,
            "database": DatabaseWriterAdapter,
        }

    def register(self, kind: str, adapter_cls: type[WriterAdapter]) -> "WriterFactory":
        self._adapters[kind] = adapter_cls
        return self

    def create(self, kind: str, **params) -> WriterAdapter:
        if kind not in self._adapters:
            raise KeyError(f"Unknown writer kind '{kind}'. Available: {list(self._adapters)}")
        return self._adapters[kind](**params)

    def write(self, kind: str, lf: pl.LazyFrame, **params) -> None:
        self.create(kind, **params).execute(lf)