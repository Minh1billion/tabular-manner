import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator
from ....domain.models.schema import Schema
from ..registry import NodeRegistry

class Merge(Operator):
    fan_in = True

    def _combine(self, lfs: list[pl.LazyFrame]) -> pl.LazyFrame:
        raise NotImplementedError("Not implemented yet.")

    def forward_many(self, plans: list[Plan]) -> tuple[Plan, str]:
        combined = self._combine([p.handle for p in plans])

        history: tuple[str, ...] = ()
        meta: dict = {}
        for p in plans:
            history += p.history
            meta.update(p.meta)
        history += (self.name,)

        merged_plan = Plan(handle=combined, history=history, meta=meta)
        return merged_plan, self.default_port

    def infer_schema_many(self, input_schemas: list[Schema]) -> Schema:
        combined = self._combine([s.to_polars() for s in input_schemas])
        return Schema.from_polars(combined.collect_schema())

@NodeRegistry.register("union")
class Union(Merge):
    label = "Union"
    category = "merge"
    optional = {"how": (str, "vertical_relaxed")}

    def _combine(self, lfs: list[pl.LazyFrame]) -> pl.LazyFrame:
        return pl.concat(lfs, how=self.how)

@NodeRegistry.register("join")
class Join(Merge):
    label = "Join"
    category = "merge"
    required = {"on": (list, str)}
    optional = {"how": (str, "inner")}
    in_ports = ("left", "right")

    def _combine(self, lfs: list[pl.LazyFrame]) -> pl.LazyFrame:
        left, right = lfs
        return left.join(right, on=self.on, how=self.how)