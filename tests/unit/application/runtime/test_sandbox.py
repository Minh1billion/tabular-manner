import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from src.engine.application.runtime.sandbox import Sandbox

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
