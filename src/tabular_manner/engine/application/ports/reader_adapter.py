import polars as pl

from abc import ABC, abstractmethod

class ReaderAdapter(ABC):
    @abstractmethod
    def execute(self) -> pl.LazyFrame:
        ...