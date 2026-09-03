import polars as pl

from ...application.ports.reader_adapter import ReaderAdapter
from ..s3.config import build_storage_options

class S3ReaderAdapter(ReaderAdapter):
    _SUPPORTED_FORMATS = ("csv", "parquet", "arrow", "json")

    def __init__(
        self,
        bucket_name: str,
        key: str,
        format: str = "csv",
        separator: str = ",",
        has_header: bool = True,
        encoding: str = "utf8",
        columns: list[str] | None = None,
        n_rows: int | None = None,
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        allow_http: bool = False,
        path_style: bool = True,
    ):
        if format not in self._SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format '{format}'. "
                f"Expected one of {self._SUPPORTED_FORMATS}."
            )

        self.path = f"s3://{bucket_name}/{key}"
        self.format = format
        self.separator = separator
        self.has_header = has_header
        self.encoding = encoding
        self.columns = columns
        self.n_rows = n_rows
        self.storage_options = build_storage_options(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            allow_http=allow_http,
            path_style=path_style,
        )

    def execute(self) -> pl.LazyFrame:
        if self.format == "csv":
            lf = pl.scan_csv(
                self.path,
                separator=self.separator,
                has_header=self.has_header,
                encoding=self.encoding,
                n_rows=self.n_rows,
                storage_options=self.storage_options,
            )
        elif self.format == "parquet":
            lf = pl.scan_parquet(self.path, n_rows=self.n_rows, storage_options=self.storage_options)
        elif self.format == "arrow":
            lf = pl.scan_ipc(self.path, n_rows=self.n_rows, storage_options=self.storage_options)
        else:
            lf = pl.scan_ndjson(self.path, n_rows=self.n_rows, storage_options=self.storage_options)

        if self.columns:
            lf = lf.select(self.columns)

        return lf
