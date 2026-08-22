from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import polars as pl


@dataclass(frozen=True)
class Plan:
    handle: pl.LazyFrame
    history: tuple[str, ...] = field(default_factory=tuple)
    meta: dict[str, Any] = field(default_factory=dict)

    def commit(self, new_handle: pl.LazyFrame, step: str = "") -> "Plan":
        return replace(self, handle=new_handle, history=self.history + (step,))

    def with_meta(self, **kwargs) -> "Plan":
        return replace(self, meta={**self.meta, **kwargs})