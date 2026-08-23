import sys
from pathlib import Path

import polars as pl
import pytest


from tabular_manner.engine.application.runtime.expression_compiler import ExpressionCompiler

@pytest.fixture
def compiler():
    return ExpressionCompiler()

class TestConstantsAndNames:
    def test_evaluates_constant(self, compiler):
        assert compiler.evaluate("42", {}) == 42

    def test_evaluates_name(self, compiler):
        assert compiler.evaluate("value", {"value": 10}) == 10

class _Holder:
    amount = 100

class TestAttributeAndCall:
    def test_evaluates_attribute_access(self, compiler):
        assert compiler.evaluate("holder.amount", {"holder": _Holder()}) == 100

    def test_evaluates_method_call(self, compiler):
        result = compiler.evaluate("pl.col('amount')", {"pl": pl})

        assert isinstance(result, pl.Expr)

    def test_evaluates_call_with_kwargs(self, compiler):
        result = compiler.evaluate("pl.lit(5)", {"pl": pl})

        assert isinstance(result, pl.Expr)

class TestBinOp:
    @pytest.mark.parametrize(
        "expression,expected",
        [
            ("1 + 2", 3),
            ("5 - 2", 3),
            ("3 * 4", 12),
            ("10 / 4", 2.5),
            ("10 % 3", 1),
        ],
    )
    def test_binary_operators(self, compiler, expression, expected):
        assert compiler.evaluate(expression, {}) == expected

class TestUnaryOp:
    def test_not_negates_value(self, compiler):
        assert compiler.evaluate("not True", {}) is False
        assert compiler.evaluate("not False", {}) is True

class TestBoolOp:
    def test_and_short_circuits_on_falsy(self, compiler):
        assert compiler.evaluate("False and (1 / 0)", {}) is False

    def test_or_short_circuits_on_truthy(self, compiler):
        assert compiler.evaluate("True or (1 / 0)", {}) is True

    def test_and_returns_last_value_when_all_truthy(self, compiler):
        assert compiler.evaluate("1 and 2", {}) == 2

    def test_or_returns_first_truthy(self, compiler):
        assert compiler.evaluate("0 or 3", {}) == 3

class TestCompare:
    @pytest.mark.parametrize(
        "expression,expected",
        [
            ("1 == 1", True),
            ("1 != 2", True),
            ("1 < 2", True),
            ("2 <= 2", True),
            ("3 > 2", True),
            ("3 >= 3", True),
        ],
    )
    def test_single_comparison(self, compiler, expression, expected):
        assert compiler.evaluate(expression, {}) is expected

    def test_chained_comparison(self, compiler):
        assert compiler.evaluate("1 < 2 < 3", {}) is True
        assert compiler.evaluate("1 < 2 < 1", {}) is False

class TestUnsupportedSyntax:
    def test_raises_for_unsupported_node(self, compiler):
        with pytest.raises(ValueError, match="Unsupported expression syntax"):
            compiler.evaluate("[1, 2, 3]", {})
