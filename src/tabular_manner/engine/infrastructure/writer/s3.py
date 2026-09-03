import polars as pl

from ...application.ports.writer_adapter import WriterAdapter
from ..s3.config import build_storage_options

class S3WriterAdapter(WriterAdapter):
    _SUPPORTED_FORMATS = ("csv", "parquet", "arrow", "json")

    def __init__(
        self,
        bucket_name: str,
        key: str,
        format: str = "csv",
        separator: str = ",",
        include_header: bool = True,
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
        self.include_header = include_header
        self.storage_options = build_storage_options(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            allow_http=allow_http,
            path_style=path_style,
        )

    def execute(self, lf: pl.LazyFrame) -> None:
        if self.format == "csv":
            lf.sink_csv(
                self.path,
                separator=self.separator,
                include_header=self.include_header,
                storage_options=self.storage_options,
            )
        elif self.format == "parquet":
            lf.sink_parquet(self.path, storage_options=self.storage_options)
        elif self.format == "arrow":
            lf.sink_ipc(self.path, storage_options=self.storage_options)
        else:
            lf.sink_ndjson(self.path, storage_options=self.storage_options)
