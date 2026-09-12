from pathlib import Path
from typing import Any, Iterator

import polars as pl
import pyarrow.ipc as ipc
import pyarrow.parquet as pq

from ...application.ports.writer_adapter import WriterAdapter

class FileWriterAdapter(WriterAdapter):
    _SUPPORTED_FORMATS = ("csv", "parquet", "arrow", "json")
    _STREAMABLE_FORMATS = ("csv", "parquet", "arrow")

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

    def execute_streaming(self, lf: pl.LazyFrame, chunk_size: int = 100_000) -> Iterator[dict[str, Any]] | None:
        if self.format not in self._STREAMABLE_FORMATS:
            return None
        return self._execute_streaming(lf, chunk_size)

    def _execute_streaming(self, lf: pl.LazyFrame, chunk_size: int) -> Iterator[dict[str, Any]]:
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)

        total: int | None = None
        try:
            total = lf.select(pl.len()).collect().item()
        except Exception:
            total = None

        processed = 0
        parquet_writer: pq.ParquetWriter | None = None
        ipc_writer: ipc.RecordBatchFileWriter | None = None
        csv_file = None
        try:
            for i, batch in enumerate(lf.collect_batches(chunk_size=chunk_size)):
                if self.format == "parquet":
                    table = batch.to_arrow()
                    if parquet_writer is None:
                        parquet_writer = pq.ParquetWriter(str(path), table.schema)
                    parquet_writer.write_table(table)
                elif self.format == "arrow":
                    table = batch.to_arrow()
                    if ipc_writer is None:
                        ipc_writer = ipc.new_file(str(path), table.schema)
                    ipc_writer.write_table(table)
                else:
                    if csv_file is None:
                        csv_file = open(path, "w", newline="")
                    batch.write_csv(
                        csv_file,
                        separator=self.separator,
                        include_header=(i == 0 and self.include_header),
                    )
                processed += batch.height
                yield {"processed": processed, "total": total}
        finally:
            if parquet_writer is not None:
                parquet_writer.close()
            if ipc_writer is not None:
                ipc_writer.close()
            if csv_file is not None:
                csv_file.close()