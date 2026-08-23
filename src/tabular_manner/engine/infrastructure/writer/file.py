import polars as pl

from ...application.ports.writer_adapter import WriterAdapter

class FileWriterAdapter(WriterAdapter):
    _SUPPORTED_FORMATS = ("csv", "parquet", "arrow", "json")

    def __init__(
        self,
        path: str,
        format: str = "csv",
        separator: str = ",",
        include_header: bool = True,
    ):
        if format not in self._SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format '{format}'. "
                f"Expected one of {self._SUPPORTED_FORMATS}."
            )

        self.path = path
        self.format = format
        self.separator = separator
        self.include_header = include_header

    def execute(self, lf: pl.LazyFrame) -> None:
        if self.format == "csv":
            lf.sink_csv(self.path, separator=self.separator, include_header=self.include_header, mkdir=True)
        elif self.format == "parquet":
            lf.sink_parquet(self.path, mkdir=True)
        elif self.format == "arrow":
            lf.sink_ipc(self.path, mkdir=True)
        elif self.format == "json":
            lf.sink_ndjson(self.path, mkdir=True)
        else:  # pragma: no cover - guarded in __init__
            raise ValueError(f"Unsupported file format '{self.format}'.")