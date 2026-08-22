from ..ports.reader_adapter import ReaderAdapter

class ReaderFactory:
    def __init__(self, adapters: dict[str, type[ReaderAdapter]] | None = None):
        self._adapters: dict[str, type[ReaderAdapter]] = dict(self._default_adapters())
        if adapters:
            self._adapters.update(adapters)

    @staticmethod
    def _default_adapters() -> dict[str, type[ReaderAdapter]]:
        from ...infrastructure.reader.database import DatabaseReaderAdapter
        from ...infrastructure.reader.file import FileReaderAdapter

        return {
            "file": FileReaderAdapter,
            "database": DatabaseReaderAdapter,
        }

    def register(self, kind: str, adapter_cls: type[ReaderAdapter]) -> "ReaderFactory":
        self._adapters[kind] = adapter_cls
        return self

    def create(self, kind: str, **params) -> ReaderAdapter:
        if kind not in self._adapters:
            raise KeyError(f"Unknown reader kind '{kind}'. Available: {list(self._adapters)}")
        return self._adapters[kind](**params)

    def read(self, kind: str, **params):
        return self.create(kind, **params).execute()