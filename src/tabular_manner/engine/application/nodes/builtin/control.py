import polars as pl

from ....domain.models.plan import Plan
from ....domain.models.operator import Operator
from ..registry import NodeRegistry
from ...runtime.expression_compiler import ExpressionCompiler
from ...runtime.sandbox import Sandbox

_COMPILER = ExpressionCompiler()

class Control(Operator):
    context = ("material_buffer",)

    def __init__(self, name: str | None = None, sandbox: Sandbox | None = None, **params):
        super().__init__(name=name, sandbox=sandbox or Sandbox(), **params)

    def _evaluate(self, plan: Plan) -> str:
        raise NotImplementedError("Not implemented yet.")

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        key = (plan.meta.get("execution_id"), id(self), hash(plan.history))
        materialized = self.material_buffer.get_or_materialize(key, plan.handle)
        checkpoint = plan.commit(materialized.lazy(), step=f"{self.name}:checkpoint")

        port = self._evaluate(checkpoint)
        return checkpoint, port

class _ColumnProxy:
    def __getattr__(self, name: str) -> pl.Expr:
        return pl.col(name)

@NodeRegistry.register("switch")
class Switch(Control):
    required = {"expression": str, "cases": (list, str)}
    optional = {"default_case": (str, "default")}

    def validate(self):
        super().validate()
        if not self.expression.strip():
            raise ValueError("'expression' must not be empty")
        if not self.cases:
            raise ValueError("'cases' must not be empty")
        if len(self.cases) != len(set(self.cases)):
            raise ValueError("'cases' must not contain duplicates")
        if self.default_case in self.cases:
            raise ValueError("'default_case' must not collide with a value in 'cases'")
        self.sandbox.check_expression(self.expression)

    def valid_ports(self) -> tuple[str, ...]:
        return tuple(self.cases) + (self.default_case,)

    def _evaluate(self, plan: Plan) -> str:
        lf = plan.handle
        expr = _COMPILER.evaluate(self.expression, {"df": _ColumnProxy(), "pl": pl})

        if not isinstance(expr, pl.Expr):
            raise TypeError("'expression' must evaluate to a polars Expr")

        result = lf.select(expr.alias("_switch_result")).collect(engine="streaming")
        if result.height != 1:
            raise ValueError(
                "'expression' must reduce to a single scalar value for 'switch' "
                f"(got {result.height} rows); aggregate it first, e.g. with .first() or .mean()"
            )

        value = result.item()
        value_str = str(value) if value is not None else None
        return value_str if value_str in self.cases else self.default_case

@NodeRegistry.register("if")
class If(Control):
    required = {"expression": str}
    ports = ("true", "false")

    def validate(self):
        super().validate()
        if not self.expression.strip():
            raise ValueError("'expression' must not be empty")
        self.sandbox.check_expression(self.expression)

    def _evaluate(self, plan: Plan) -> str:
        lf = plan.handle
        expr = _COMPILER.evaluate(self.expression, {"df": _ColumnProxy(), "pl": pl})

        if not isinstance(expr, pl.Expr):
            raise TypeError("'expression' must evaluate to a polars Expr")

        result = lf.select(expr.alias("_if_result")).collect(engine="streaming")
        if result.height != 1:
            result = lf.select(expr.alias("_if_result").all()).collect(engine="streaming")

        dtype = result.schema["_if_result"]
        if dtype != pl.Boolean:
            raise TypeError(f"'expression' must evaluate to a boolean, got {dtype}")

        return "true" if bool(result.item()) else "false"