import polars as pl

from ...application.ports.writer_adapter import WriterAdapter

class DatabaseWriterAdapter(WriterAdapter):
    _VALID_MODES = ("append", "replace", "fail")

    def __init__(
        self,
        dsn: str,
        table: str,
        if_table_exists: str = "append",
    ):
        if if_table_exists not in self._VALID_MODES:
            raise ValueError(
                f"Unsupported if_table_exists '{if_table_exists}'. "
                f"Expected one of {self._VALID_MODES}."
            )

        self.dsn = dsn
        self.table = table
        self.if_table_exists = if_table_exists

    def execute(self, lf: pl.LazyFrame) -> None:
        df = lf.collect(engine="streaming")
        df.write_database(
            table_name=self.table,
            connection=self.dsn,
            if_table_exists=self.if_table_exists,
        )