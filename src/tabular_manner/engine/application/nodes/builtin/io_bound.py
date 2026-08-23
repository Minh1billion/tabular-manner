import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator
from ..registry import NodeRegistry

class SourceIO(Operator):
    def _stream(self) -> pl.LazyFrame:
        raise NotImplementedError("Not implemented yet.")

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        fetched = self._stream()
        return plan.commit(fetched, step=self.name), self.default_port

class SinkIO(Operator):
    def _persist(self, lf: pl.LazyFrame) -> None:
        raise NotImplementedError("Not implemented yet.")

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        self._persist(plan.handle)
        return plan, self.default_port

@NodeRegistry.register("fetch_internal")
class FetchInternal(SourceIO):
    label = "Fetch (Internal)"
    category = "io"
    required = {"key": str}
    optional = {"bucket": (str, None)}
    context = ("resource_storage",)

    def _stream(self) -> pl.LazyFrame:
        return self.resource_storage.load(self.key, bucket=self.bucket)

@NodeRegistry.register("fetch_csv")
class FetchCsv(SourceIO):
    label = "Fetch CSV"
    category = "io"
    required = {"path": str}
    optional = {"separator": (str, ","), "has_header": (bool, True), "encoding": (str, "utf8")}
    context = ("reader_factory",)

    def _stream(self) -> pl.LazyFrame:
        return self.reader_factory.read(
            "file",
            path=self.path,
            format="csv",
            separator=self.separator,
            has_header=self.has_header,
            encoding=self.encoding,
        )

@NodeRegistry.register("fetch_parquet")
class FetchParquet(SourceIO):
    label = "Fetch Parquet"
    category = "io"
    required = {"path": str}
    optional = {"columns": ((list, str), None), "n_rows": (int, None)}
    context = ("reader_factory",)

    def _stream(self) -> pl.LazyFrame:
        return self.reader_factory.read(
            "file",
            path=self.path,
            format="parquet",
            columns=self.columns,
            n_rows=self.n_rows,
        )

@NodeRegistry.register("fetch_arrow")
class FetchArrow(SourceIO):
    label = "Fetch Arrow"
    category = "io"
    required = {"path": str}
    context = ("reader_factory",)

    def _stream(self) -> pl.LazyFrame:
        return self.reader_factory.read("file", path=self.path, format="arrow")

@NodeRegistry.register("fetch_s3")
class FetchS3(SourceIO):
    label = "Fetch S3"
    category = "io"
    required = {"bucket": str, "key": str}
    optional = {"format": (str, "parquet"), "region": (str, None), "storage_options": (dict, None)}

    def _stream(self) -> pl.LazyFrame:
        uri = f"s3://{self.bucket}/{self.key}"
        storage_options = dict(self.storage_options or {})
        if self.region:
            storage_options.setdefault("region", self.region)

        if self.format == "csv":
            return pl.scan_csv(uri, storage_options=storage_options)
        return pl.scan_parquet(uri, storage_options=storage_options)

@NodeRegistry.register("fetch_postgres")
class FetchPostgres(SourceIO):
    label = "Fetch Postgres"
    category = "io"
    required = {"dsn": str, "table": str}
    optional = {
        "query": (str, None),
        "partition_on": (str, None),
        "partition_num": (int, None),
    }
    context = ("reader_factory",)

    def _stream(self) -> pl.LazyFrame:
        return self.reader_factory.read(
            "database",
            dsn=self.dsn,
            table=self.table,
            query=self.query,
            partition_on=self.partition_on,
            partition_num=self.partition_num,
        )

@NodeRegistry.register("push_internal")
class PushInternal(SinkIO):
    label = "Export (Internal)"
    category = "io"
    required = {"key": str}
    optional = {"bucket": (str, None)}
    context = ("resource_storage",)

    def _persist(self, lf: pl.LazyFrame) -> None:
        self.resource_storage.save(self.key, lf, bucket=self.bucket)

@NodeRegistry.register("push_csv")
class PushCsv(SinkIO):
    label = "Export CSV"
    category = "io"
    required = {"path": str}
    optional = {"separator": (str, ","), "include_header": (bool, True)}
    context = ("writer_factory",)

    def _persist(self, lf: pl.LazyFrame) -> None:
        self.writer_factory.write(
            "file",
            lf,
            path=self.path,
            format="csv",
            separator=self.separator,
            include_header=self.include_header,
        )

@NodeRegistry.register("push_parquet")
class PushParquet(SinkIO):
    label = "Export Parquet"
    category = "io"
    required = {"path": str}
    context = ("writer_factory",)

    def _persist(self, lf: pl.LazyFrame) -> None:
        self.writer_factory.write("file", lf, path=self.path, format="parquet")

@NodeRegistry.register("push_arrow")
class PushArrow(SinkIO):
    label = "Export Arrow"
    category = "io"
    required = {"path": str}
    context = ("writer_factory",)

    def _persist(self, lf: pl.LazyFrame) -> None:
        self.writer_factory.write("file", lf, path=self.path, format="arrow")

@NodeRegistry.register("push_postgres")
class PushPostgres(SinkIO):
    label = "Export Postgres"
    category = "io"
    required = {"dsn": str, "table": str}
    optional = {"if_table_exists": (str, "append")}
    context = ("writer_factory",)

    def _persist(self, lf: pl.LazyFrame) -> None:
        self.writer_factory.write(
            "database",
            lf,
            dsn=self.dsn,
            table=self.table,
            if_table_exists=self.if_table_exists,
        )