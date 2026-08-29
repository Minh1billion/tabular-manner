import polars as pl

from abc import ABC, abstractmethod

class ReaderAdapter(ABC):
    @abstractmethod
    def execute(self) -> pl.LazyFrame:
        ...

    def sample_schema(self) -> pl.Schema:
        return self.execute().collect_schema()