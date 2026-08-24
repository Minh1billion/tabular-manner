import pytest

from tests.support.paths import samples_dir

def _run(engine, load_spec, mock_name: str) -> dict:
    spec = load_spec(mock_name)
    events = list(engine.execution.execute(spec=spec))

    failed = [e for e in events if e["event"] == "failed"]
    assert not failed, f"{mock_name} failed: {failed}"

    completed = [e for e in events if e["event"] == "completed"]
    assert completed, f"{mock_name} never completed"

    return completed[0]["data"]

def _leaves_by_node(result: dict) -> dict:
    return {leaf["node_id"]: leaf for leaf in result["leaves"]}

class TestBasicCleanPipeline:
    def test_produces_single_branch_with_all_columns(self, engine, load_spec):
        result = _run(engine, load_spec, "basic_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"4"}
        assert leaves["4"]["columns"] == ["customer", "amount", "quantity"]
        assert leaves["4"]["history"] == [
            "Fetch Data",
            "Select Columns",
            "Fill Missing (Mean)",
        ]

class TestFanoutCleanPipeline:
    def test_produces_two_independent_branches(self, engine, load_spec):
        result = _run(engine, load_spec, "fanout_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"4", "6"}
        assert leaves["4"]["columns"] == ["customer", "amount", "quantity"]
        assert leaves["6"]["columns"] == ["customer"]

    def test_both_branches_share_the_same_upstream_history(self, engine, load_spec):
        result = _run(engine, load_spec, "fanout_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        shared_prefix = ["Fetch Data", "Select Columns", "Fill Missing (Mean)"]
        assert leaves["4"]["history"] == shared_prefix
        assert leaves["6"]["history"] == shared_prefix + ["Select Customer Only"]

class TestJoinPipeline:
    def test_joins_customers_with_amounts_on_customer_column(self, engine, load_spec):
        result = _run(engine, load_spec, "join_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"4"}
        assert leaves["4"]["columns"] == ["customer", "amount"]
        assert leaves["4"]["history"] == [
            "Fetch Customers",
            "Fetch Mid",
            "Join Customers With Amounts",
        ]

class TestUnionPipeline:
    def test_unions_two_branches_from_the_same_source(self, engine, load_spec):
        result = _run(engine, load_spec, "union_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"7"}
        assert leaves["7"]["columns"] == ["customer", "amount", "quantity"]
        assert leaves["7"]["history"] == [
            "Fetch Data",
            "Branch A Select",
            "Branch A Fill",
            "Fetch Data",
            "Branch B Select",
            "Branch B Fill",
            "Union Branches",
        ]

class TestAllMocksRunCleanly:
    @pytest.mark.parametrize("mock_path", sorted(samples_dir().glob("*.json")), ids=lambda p: p.name)
    def test_pipeline_completes_without_failing(self, engine, load_spec, mock_path):
        result = _run(engine, load_spec, mock_path.name)
        assert len(result["leaves"]) >= 1