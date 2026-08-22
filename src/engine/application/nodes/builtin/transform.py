import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator
from ..registry import NodeRegistry

class Transform(Operator):
    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        raise NotImplementedError("Not implemented yet.")

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        applied = self._apply(plan.handle)
        return plan.commit(applied, step=self.name), self.default_port

@NodeRegistry.register("select")
class Select(Transform):
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.select(self.columns)

@NodeRegistry.register("fill_mean")
class FillMean(Transform):
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(strategy="mean") for c in self.columns
        )