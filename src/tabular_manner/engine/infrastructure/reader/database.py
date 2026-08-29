import polars as pl

from ...application.ports.reader_adapter import ReaderAdapter

class DatabaseReaderAdapter(ReaderAdapter):
    def __init__(
        self,
        dsn: str,
        table: str | None = None,
        query: str | None = None,
        partition_on: str | None = None,
        partition_num: int | None = None,
    ):
        if not table and not query:
            raise ValueError("Either 'table' or 'query' must be provided.")

        self.dsn = dsn
        self.table = table
        self.query = query
        self.partition_on = partition_on
        self.partition_num = partition_num

    def execute(self) -> pl.LazyFrame:
        query = self.query or f"SELECT * FROM {self.table}"

        kwargs = {}
        if self.partition_on:
            kwargs["partition_on"] = self.partition_on
        if self.partition_num:
            kwargs["partition_num"] = self.partition_num

        df = pl.read_database_uri(query=query, uri=self.dsn, **kwargs)
        return df.lazy()

    def sample_schema(self) -> pl.Schema:
        base = self.query or f"SELECT * FROM {self.table}"
        probe_query = f"SELECT * FROM ({base}) AS __schema_probe__ LIMIT 1"
        df = pl.read_database_uri(query=probe_query, uri=self.dsn)
        return df.lazy().collect_schema()