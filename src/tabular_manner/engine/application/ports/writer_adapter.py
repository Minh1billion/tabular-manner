from typing import Any, Iterator

import polars as pl

from abc import ABC, abstractmethod

class WriterAdapter(ABC):
    @abstractmethod
    def execute(self, lf: pl.LazyFrame) -> None:
        ...

    def execute_streaming(
        self,
        lf: pl.LazyFrame,
        chunk_size: int = 100_000,
        progress_threshold_rows: int | None = 500_000,
    ) -> Iterator[dict[str, Any]] | None:
        return None