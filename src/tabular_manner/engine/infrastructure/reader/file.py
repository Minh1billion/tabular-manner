import polars as pl

from ...application.ports.reader_adapter import ReaderAdapter

class FileReaderAdapter(ReaderAdapter):
    _SUPPORTED_FORMATS = ("csv", "parquet", "arrow", "json")

    def __init__(
        self,
        path: str,
        format: str = "csv",
        separator: str = ",",
        has_header: bool = True,
        encoding: str = "utf8",
        columns: list[str] | None = None,
        n_rows: int | None = None,
    ):
        if format not in self._SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format '{format}'. "
                f"Expected one of {self._SUPPORTED_FORMATS}."
            )

        self.path = path
        self.format = format
        self.separator = separator
        self.has_header = has_header
        self.encoding = encoding
        self.columns = columns
        self.n_rows = n_rows

    def execute(self) -> pl.LazyFrame:
        if self.format == "csv":
            lf = pl.scan_csv(
                self.path,
                separator=self.separator,
                has_header=self.has_header,
                encoding=self.encoding,
                n_rows=self.n_rows,
            )
        elif self.format == "parquet":
            lf = pl.scan_parquet(self.path, n_rows=self.n_rows)
        elif self.format == "arrow":
            lf = pl.scan_ipc(self.path, n_rows=self.n_rows)
        elif self.format == "json":
            lf = pl.scan_ndjson(self.path, n_rows=self.n_rows)
        else:  # pragma: no cover - guarded in __init__
            raise ValueError(f"Unsupported file format '{self.format}'.")

        if self.columns:
            lf = lf.select(self.columns)

        return lf