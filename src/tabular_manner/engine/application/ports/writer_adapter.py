import polars as pl

from abc import ABC, abstractmethod

class WriterAdapter(ABC):
    @abstractmethod
    def execute(self, lf: pl.LazyFrame) -> None:
        ...