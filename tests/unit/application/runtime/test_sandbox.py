import pytest

from tabular_manner.engine.application.runtime.sandbox import Sandbox

@pytest.fixture
def sandbox():
    return Sandbox()

class TestSandboxBlocksArbitraryPlCalls:
    @pytest.mark.parametrize(
        "expression",
        [
            "pl.read_csv('/etc/passwd')",
            "pl.read_parquet('/etc/passwd')",
            "pl.scan_csv('/etc/passwd')",
            "pl.scan_parquet('http://169.254.169.254/latest/meta-data')",
            "pl.read_csv('/etc/passwd').write_parquet('/tmp/x.parquet')",
            "pl.DataFrame({'a': [1]})",
            "pl.selectors.numeric()",
            "pl.Config.set_verbose(True)",
            "df.amount.map_elements(pl.read_csv)",
            "df.amount.map_elements(pl.DataFrame)",
            "df.amount.map_batches(pl.scan_parquet)",
            "df.amount +",
            "def f(): pass",
        ],
    )
    def test_blocked(self, sandbox, expression):
        with pytest.raises(ValueError):
            sandbox.check_expression(expression)

    def test_blocked_expression_never_reaches_eval(self, sandbox, tmp_path):
        target = tmp_path / "should_not_exist.parquet"
        expression = f"pl.read_csv('/etc/passwd').write_parquet('{target}')"

        with pytest.raises(ValueError):
            sandbox.check_expression(expression)

        assert not target.exists()

class TestSandboxAdversarial:
    @pytest.mark.parametrize(
        "expression",
        [
            "__import__('os').system('id')",
            "().__class__.__bases__[0].__subclasses__()",
            "df.__class__",
            "df.amount.__class__.__bases__",
            "getattr(df, '__class__')",
            "setattr(df, 'x', 1)",
            "(1).__class__",
            "().__class__",
            "df.amount.__init__.__globals__",
            "(lambda: 1)()",
            "(lambda x: x.__class__)(df)",
            "exec('1')",
            "eval('1')",
            "compile('1', '<s>', 'eval')",
            "[x for x in range(3)]",
            "{x for x in range(3)}",
            "{x: x for x in range(3)}",
            "(x for x in range(3))",
            "1 if True else 2",
            "(x := 1)",
            "df['amount']",
            "df.amount[0]",
            "f'{df}'",
            "import os",
            "globals()",
            "locals()",
            "vars(df)",
            "type(df)",
            "df.amount.__doc__",
            "pl.__loader__",
            "pl.__builtins__",
            "df.amount.__reduce__()",
            "df.amount.__subclasshook__",
            "yield 1",
            "assert False",
            "del df",
        ],
    )
    def test_blocked(self, sandbox, expression):
        with pytest.raises(ValueError):
            sandbox.check_expression(expression)

    def test_blocked_dunder_attribute_regardless_of_base(self, sandbox):
        with pytest.raises(ValueError):
            sandbox.check_expression("pl.col('a')._private_field")

    def test_blocked_free_function_call_without_attribute(self, sandbox):
        with pytest.raises(ValueError):
            sandbox.check_expression("str(df)")

    def test_allowed_names_are_enforced_even_for_arbitrary_identifiers(self, sandbox):
        with pytest.raises(ValueError):
            sandbox.check_expression("os", allowed_names=frozenset({"df", "pl"}))

class TestSandboxAllowsLegitimateExpressions:
    @pytest.mark.parametrize(
        "expression",
        [
            "df.amount.mean() >= 150",
            "df.amount.len() > 0",
            "df.amount.mean() >= 100 and df.quantity.sum() > 0",
            "pl.lit(True)",
            "pl.col('amount').mean() > 10",
            (
                "pl.when(df.amount.mean() >= 150).then(pl.lit('high'))"
                ".when(df.amount.mean() >= 80).then(pl.lit('mid'))"
                ".otherwise(pl.lit('low'))"
            ),
        ],
    )
    def test_allowed(self, sandbox, expression):
        sandbox.check_expression(expression)