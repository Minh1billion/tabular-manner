import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator
from ..registry import NodeRegistry
from ...runtime.expression_compiler import ExpressionCompiler
from ...runtime.sandbox import Sandbox

class _ColumnProxy:
    def __getattr__(self, name: str) -> pl.Expr:
        return pl.col(name)

class Transform(Operator):
    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        raise NotImplementedError("Not implemented yet.")

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        applied = self._apply(plan.handle)
        return plan.commit(applied, step=self.name), self.default_port

@NodeRegistry.register("select")
class Select(Transform):
    label = "Select Columns"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.select(self.columns)

@NodeRegistry.register("drop")
class Drop(Transform):
    label = "Drop Columns"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.drop(self.columns)

@NodeRegistry.register("limit")
class Limit(Transform):
    label = "Limit Rows"
    category = "transform"
    required = {"n": int}

    def validate(self):
        super().validate()
        if self.n < 0:
            raise ValueError("'n' must be >= 0")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.limit(self.n)

@NodeRegistry.register("head")
class Head(Transform):
    label = "Head Rows"
    category = "transform"
    required = {"n": int}

    def validate(self):
        super().validate()
        if self.n < 0:
            raise ValueError("'n' must be >= 0")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.head(self.n)

@NodeRegistry.register("tail")
class Tail(Transform):
    label = "Tail Rows"
    category = "transform"
    required = {"n": int}

    def validate(self):
        super().validate()
        if self.n < 0:
            raise ValueError("'n' must be >= 0")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.tail(self.n)

@NodeRegistry.register("explode")
class Explode(Transform):
    label = "Explode Columns"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.explode(self.columns, empty_as_null=True)

@NodeRegistry.register("group_by")
class GroupBy(Transform):
    label = "Group By"
    category = "transform"
    required = {"by": (list, str), "aggregations": dict}

    _ALLOWED_AGGS = frozenset({"sum", "mean", "min", "max", "count", "median", "std", "first", "last"})

    def validate(self):
        super().validate()
        if not self.aggregations:
            raise ValueError("'aggregations' must not be empty")
        for column, agg in self.aggregations.items():
            if not isinstance(column, str) or not isinstance(agg, str):
                raise TypeError("'aggregations' keys and values must be strings")
            if agg not in self._ALLOWED_AGGS:
                raise ValueError(f"Unknown aggregation '{agg}' for column '{column}'")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.group_by(self.by).agg(
            getattr(pl.col(c), agg)().alias(c) for c, agg in self.aggregations.items()
        )

@NodeRegistry.register("log")
class Log(Transform):
    label = "Log Transform"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"base": (float, None)}

    def validate(self):
        super().validate()
        if self.base is not None and self.base <= 0:
            raise ValueError("'base' must be > 0")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).log(self.base) if self.base is not None else pl.col(c).log()
            for c in self.columns
        )

@NodeRegistry.register("zscore_normalize")
class ZScoreNormalize(Transform):
    label = "Z-Score Normalize"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            ((pl.col(c) - pl.col(c).mean()) / pl.col(c).std()).alias(c) for c in self.columns
        )

@NodeRegistry.register("minmax_normalize")
class MinMaxNormalize(Transform):
    label = "Min-Max Normalize"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            ((pl.col(c) - pl.col(c).min()) / (pl.col(c).max() - pl.col(c).min())).alias(c)
            for c in self.columns
        )

@NodeRegistry.register("fill_mean")
class FillMean(Transform):
    label = "Fill Missing (Mean)"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(strategy="mean") for c in self.columns
        )

@NodeRegistry.register("fill_null")
class FillNull(Transform):
    label = "Fill Missing (Value)"
    category = "transform"
    required = {"columns": (list, str), "value": object}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(self.value) for c in self.columns
        )

@NodeRegistry.register("drop_nulls")
class DropNulls(Transform):
    label = "Drop Null Rows"
    category = "transform"
    optional = {"columns": ((list, str), None)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.drop_nulls(subset=self.columns)

@NodeRegistry.register("drop_duplicates")
class DropDuplicates(Transform):
    label = "Drop Duplicate Rows"
    category = "transform"
    optional = {"subset": ((list, str), None), "keep": (str, "first")}

    def validate(self):
        super().validate()
        if self.keep not in ("first", "last", "any", "none"):
            raise ValueError("'keep' must be one of 'first', 'last', 'any', 'none'")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.unique(subset=self.subset, keep=self.keep)

@NodeRegistry.register("rename")
class Rename(Transform):
    label = "Rename Columns"
    category = "transform"
    required = {"mapping": dict}

    def validate(self):
        super().validate()
        if not self.mapping:
            raise ValueError("'mapping' must not be empty")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in self.mapping.items()):
            raise TypeError("'mapping' keys and values must be strings")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.rename(self.mapping)

@NodeRegistry.register("sort")
class Sort(Transform):
    label = "Sort Rows"
    category = "transform"
    required = {"by": (list, str)}
    optional = {"descending": (bool, False)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.sort(self.by, descending=self.descending)

@NodeRegistry.register("cast")
class Cast(Transform):
    label = "Cast Column Type"
    category = "transform"
    required = {"types": dict}

    def validate(self):
        super().validate()
        if not self.types:
            raise ValueError("'types' must not be empty")
        for column, dtype_name in self.types.items():
            if not isinstance(column, str) or not isinstance(dtype_name, str):
                raise TypeError("'types' keys and values must be strings")
            dtype = getattr(pl, dtype_name, None)
            if not isinstance(dtype, type) or not issubclass(dtype, pl.DataType):
                raise ValueError(f"Unknown polars dtype '{dtype_name}'")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).cast(getattr(pl, t)) for c, t in self.types.items()
        )

class _ExpressionTransform(Transform):
    required = {"expression": str}
    COMPILER = ExpressionCompiler()

    def __init__(self, name: str | None = None, sandbox: Sandbox | None = None, **params):
        super().__init__(name=name, sandbox=sandbox or Sandbox(), **params)

    def validate(self):
        super().validate()
        if not self.expression.strip():
            raise ValueError("'expression' must not be empty")
        self.sandbox.check_expression(self.expression)

    def _compile_expr(self) -> pl.Expr:
        expr = self.COMPILER.evaluate(self.expression, {"df": _ColumnProxy(), "pl": pl})
        if not isinstance(expr, pl.Expr):
            raise TypeError("'expression' must evaluate to a polars Expr")
        return expr

@NodeRegistry.register("filter")
class Filter(_ExpressionTransform):
    label = "Filter Rows"
    category = "transform"

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.filter(self._compile_expr())

@NodeRegistry.register("derive")
class Derive(_ExpressionTransform):
    label = "Derive Column"
    category = "transform"
    required = {**_ExpressionTransform.required, "column": str}

    def validate(self):
        super().validate()
        if not self.column.strip():
            raise ValueError("'column' must not be empty")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(self._compile_expr().alias(self.column))