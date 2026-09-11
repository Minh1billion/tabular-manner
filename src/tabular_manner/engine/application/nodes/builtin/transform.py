import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator, SchemaStrategy
from ....domain.models.schema import Schema
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

    def infer_schema(self, input_schema: Schema) -> Schema:
        if self.schema_strategy is SchemaStrategy.DECLARED:
            return self.declared_schema(input_schema)
        applied = self._apply(input_schema.to_polars())
        return Schema.from_polars(applied.collect_schema())

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

@NodeRegistry.register("abs")
class Abs(Transform):
    label = "Absolute Value"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(pl.col(c).abs() for c in self.columns)

@NodeRegistry.register("round")
class Round(Transform):
    label = "Round"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"decimals": (int, 0)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(pl.col(c).round(self.decimals) for c in self.columns)

@NodeRegistry.register("clip")
class Clip(Transform):
    label = "Clip Values"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"lower": (float, None), "upper": (float, None)}

    def validate(self):
        super().validate()
        if self.lower is None and self.upper is None:
            raise ValueError("at least one of 'lower' or 'upper' must be set")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(pl.col(c).clip(self.lower, self.upper) for c in self.columns)

@NodeRegistry.register("sqrt")
class Sqrt(Transform):
    label = "Square Root"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(pl.col(c).sqrt() for c in self.columns)

@NodeRegistry.register("power")
class Power(Transform):
    label = "Power"
    category = "transform"
    required = {"columns": (list, str), "exponent": float}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(pl.col(c).pow(self.exponent) for c in self.columns)

@NodeRegistry.register("fill_forward")
class FillForward(Transform):
    label = "Fill Missing (Forward)"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(strategy="forward") for c in self.columns
        )

@NodeRegistry.register("fill_backward")
class FillBackward(Transform):
    label = "Fill Missing (Backward)"
    category = "transform"
    required = {"columns": (list, str)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).fill_null(strategy="backward") for c in self.columns
        )

@NodeRegistry.register("str_case")
class StrCase(Transform):
    label = "Change Text Case"
    category = "transform"
    required = {"columns": (list, str), "case": str}

    def validate(self):
        super().validate()
        if self.case not in ("upper", "lower", "title"):
            raise ValueError("'case' must be one of 'upper', 'lower', 'title'")

    def _column_expr(self, c: str) -> pl.Expr:
        if self.case == "upper":
            return pl.col(c).str.to_uppercase()
        if self.case == "lower":
            return pl.col(c).str.to_lowercase()
        return pl.col(c).str.to_titlecase()

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(self._column_expr(c) for c in self.columns)

@NodeRegistry.register("str_strip")
class StrStrip(Transform):
    label = "Strip Whitespace"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"characters": (str, None)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).str.strip_chars(self.characters) for c in self.columns
        )

@NodeRegistry.register("str_replace")
class StrReplace(Transform):
    label = "Replace Text"
    category = "transform"
    required = {"columns": (list, str), "pattern": str, "value": str}
    optional = {"literal": (bool, False)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).str.replace_all(self.pattern, self.value, literal=self.literal)
            for c in self.columns
        )

@NodeRegistry.register("rank")
class Rank(Transform):
    label = "Rank"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"method": (str, "average"), "descending": (bool, False)}

    _ALLOWED_METHODS = frozenset({"average", "min", "max", "dense", "ordinal", "random"})

    def validate(self):
        super().validate()
        if self.method not in self._ALLOWED_METHODS:
            raise ValueError(f"'method' must be one of {sorted(self._ALLOWED_METHODS)}")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).rank(method=self.method, descending=self.descending) for c in self.columns
        )

@NodeRegistry.register("cumulative_sum")
class CumulativeSum(Transform):
    label = "Cumulative Sum"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"reverse": (bool, False)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).cum_sum(reverse=self.reverse) for c in self.columns
        )

@NodeRegistry.register("shift")
class Shift(Transform):
    label = "Shift (Lag/Lead)"
    category = "transform"
    required = {"columns": (list, str), "n": int}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(pl.col(c).shift(self.n) for c in self.columns)

@NodeRegistry.register("add_row_index")
class AddRowIndex(Transform):
    label = "Add Row Index"
    category = "transform"
    optional = {"index_name": (str, "index"), "offset": (int, 0)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_row_index(name=self.index_name, offset=self.offset)

@NodeRegistry.register("bin")
class Bin(Transform):
    label = "Bin Into Ranges"
    category = "transform"
    required = {"column": str, "breaks": (list, float)}
    optional = {"labels": ((list, str), None), "output_column": (str, None)}

    def validate(self):
        super().validate()
        if not self.breaks:
            raise ValueError("'breaks' must not be empty")
        if self.labels is not None and len(self.labels) != len(self.breaks) + 1:
            raise ValueError("'labels' must have exactly len(breaks) + 1 entries")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        out_column = self.output_column or f"{self.column}_bin"
        return lf.with_columns(
            pl.col(self.column).cut(self.breaks, labels=self.labels).alias(out_column)
        )

@NodeRegistry.register("extract_regex")
class ExtractRegex(Transform):
    label = "Extract via Regex"
    category = "transform"
    required = {"column": str, "pattern": str}
    optional = {"group": (int, 1), "output_column": (str, None)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        out_column = self.output_column or f"{self.column}_extracted"
        return lf.with_columns(
            pl.col(self.column).str.extract(self.pattern, self.group).alias(out_column)
        )

@NodeRegistry.register("parse_date")
class ParseDate(Transform):
    label = "Parse Date"
    category = "transform"
    required = {"columns": (list, str)}
    optional = {"format": (str, None)}

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.with_columns(
            pl.col(c).str.to_date(self.format) for c in self.columns
        )

@NodeRegistry.register("date_part")
class DatePart(Transform):
    label = "Extract Date Part"
    category = "transform"
    required = {"column": str, "part": str}
    optional = {"output_column": (str, None)}

    _ALLOWED_PARTS = frozenset({
        "year", "quarter", "month", "week", "weekday", "day",
        "ordinal_day", "hour", "minute", "second",
    })

    def validate(self):
        super().validate()
        if self.part not in self._ALLOWED_PARTS:
            raise ValueError(f"'part' must be one of {sorted(self._ALLOWED_PARTS)}")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        out_column = self.output_column or f"{self.column}_{self.part}"
        return lf.with_columns(
            getattr(pl.col(self.column).dt, self.part)().alias(out_column)
        )

@NodeRegistry.register("unpivot")
class Unpivot(Transform):
    label = "Unpivot (Melt)"
    category = "transform"
    optional = {
        "index": ((list, str), None),
        "on": ((list, str), None),
        "variable_name": (str, None),
        "value_name": (str, None),
    }

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        return lf.unpivot(
            index=self.index,
            on=self.on,
            variable_name=self.variable_name,
            value_name=self.value_name,
        )

@NodeRegistry.register("map_values")
class MapValues(Transform):
    label = "Map Values"
    category = "transform"
    required = {"column": str, "mapping": dict}
    optional = {"default": (object, None)}

    def validate(self):
        super().validate()
        if not self.mapping:
            raise ValueError("'mapping' must not be empty")

    def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
        if self.default is not None:
            expr = pl.col(self.column).replace_strict(self.mapping, default=self.default)
        else:
            expr = pl.col(self.column).replace(self.mapping)
        return lf.with_columns(expr)

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