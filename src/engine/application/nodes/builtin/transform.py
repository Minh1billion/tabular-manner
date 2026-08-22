import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator
from ..registry import NodeRegistry
from ...runtime.expression_compiler import ExpressionCompiler
from ...runtime.sandbox import Sandbox

_COMPILER = ExpressionCompiler()

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
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.select(self.columns)

@NodeRegistry.register("drop")
class Drop(Transform):
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.drop(self.columns)

@NodeRegistry.register("limit")
class Limit(Transform):
    required = {"n": int}

    def validate(self):
        super().validate()
        if self.n < 0:
            raise ValueError("'n' must be >= 0")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.limit(self.n)

@NodeRegistry.register("fill_mean")
class FillMean(Transform):
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(strategy="mean") for c in self.columns
        )

@NodeRegistry.register("fill_null")
class FillNull(Transform):
    required = {"columns": (list, str), "value": object}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(self.value) for c in self.columns
        )

@NodeRegistry.register("drop_nulls")
class DropNulls(Transform):
    optional = {"columns": ((list, str), None)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.drop_nulls(subset=self.columns)

@NodeRegistry.register("drop_duplicates")
class DropDuplicates(Transform):
    optional = {"subset": ((list, str), None), "keep": (str, "first")}

    def validate(self):
        super().validate()
        if self.keep not in ("first", "last", "any", "none"):
            raise ValueError("'keep' must be one of 'first', 'last', 'any', 'none'")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.unique(subset=self.subset, keep=self.keep)

@NodeRegistry.register("rename")
class Rename(Transform):
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
    required = {"by": (list, str)}
    optional = {"descending": (bool, False)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.sort(self.by, descending=self.descending)

@NodeRegistry.register("cast")
class Cast(Transform):
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

    def __init__(self, name: str | None = None, sandbox: Sandbox | None = None, **params):
        super().__init__(name=name, sandbox=sandbox or Sandbox(), **params)

    def validate(self):
        super().validate()
        if not self.expression.strip():
            raise ValueError("'expression' must not be empty")
        self.sandbox.check_expression(self.expression)

    def _compile_expr(self) -> pl.Expr:
        expr = _COMPILER.evaluate(self.expression, {"df": _ColumnProxy(), "pl": pl})
        if not isinstance(expr, pl.Expr):
            raise TypeError("'expression' must evaluate to a polars Expr")
        return expr

@NodeRegistry.register("filter")
class Filter(_ExpressionTransform):
    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.filter(self._compile_expr())

@NodeRegistry.register("derive")
class Derive(_ExpressionTransform):
    required = {**_ExpressionTransform.required, "column": str}

    def validate(self):
        super().validate()
        if not self.column.strip():
            raise ValueError("'column' must not be empty")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(self._compile_expr().alias(self.column))