import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.bootstrap import build_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MOCKS_DIR = PROJECT_ROOT / "samples" / "json"
STORAGE_ROOT = PROJECT_ROOT / ".tm" / "resource_storage"

@pytest.fixture
def engine():
    return build_engine(storage_root=str(STORAGE_ROOT))

def _run(engine, mock_name: str) -> dict:
    spec = json.loads((MOCKS_DIR / mock_name).read_text())
    events = list(engine.execution.execute(spec=spec))

    failed = [e for e in events if e["event"] == "failed"]
    assert not failed, f"{mock_name} failed: {failed}"

    completed = [e for e in events if e["event"] == "completed"]
    assert completed, f"{mock_name} never completed"

    return completed[0]["data"]

def _leaves_by_node(result: dict) -> dict:
    return {leaf["node_id"]: leaf for leaf in result["leaves"]}

class TestBasicCleanPipeline:
    def test_produces_single_branch_with_all_columns(self, engine):
        result = _run(engine, "basic_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"4"}
        assert leaves["4"]["columns"] == ["customer", "amount", "quantity"]
        assert leaves["4"]["history"] == [
            "Fetch Data",
            "Select Columns",
            "Fill Missing (Mean)",
        ]

class TestConditionalCleanPipeline:
    def test_takes_false_branch_and_reduces_to_customer_column(self, engine):
        result = _run(engine, "conditional_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"7"}
        assert leaves["7"]["columns"] == ["customer"]
        assert leaves["7"]["history"] == [
            "Fetch Data",
            "Select Columns",
            "Fill Missing (Mean)",
            "Check Row Count:checkpoint",
            "Select Customer Only",
        ]

class TestFanoutCleanPipeline:
    def test_produces_two_independent_branches(self, engine):
        result = _run(engine, "fanout_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"4", "6"}
        assert leaves["4"]["columns"] == ["customer", "amount", "quantity"]
        assert leaves["6"]["columns"] == ["customer"]

    def test_both_branches_share_the_same_upstream_history(self, engine):
        result = _run(engine, "fanout_clean_pipeline.json")
        leaves = _leaves_by_node(result)

        shared_prefix = ["Fetch Data", "Select Columns", "Fill Missing (Mean)"]
        assert leaves["4"]["history"] == shared_prefix
        assert leaves["6"]["history"] == shared_prefix + ["Select Customer Only"]

class TestJoinPipeline:
    def test_joins_customers_with_amounts_on_customer_column(self, engine):
        result = _run(engine, "join_pipeline.json")
        leaves = _leaves_by_node(result)

        assert set(leaves) == {"4"}
        assert leaves["4"]["columns"] == ["customer", "amount"]
        assert leaves["4"]["history"] == [
            "Fetch Customers",
            "Fetch Mid",
            "Join Customers With Amounts",
        ]

class TestSwitchAmountBucketPipeline:
    def test_routes_to_mid_bucket_for_this_dataset(self, engine):
        result = _run(engine, "switch_amount_bucket_pipeline.json")
        leaves = _leaves_by_node(result)

        # dataset's mean amount is ~99.6: < 150 (not 'high') and >= 80 (so 'mid', not 'low')
        assert set(leaves) == {"7"}
        assert leaves["7"]["columns"] == ["customer", "amount"]
        assert leaves["7"]["history"] == [
            "Fetch Data",
            "Select Columns",
            "Fill Missing (Mean)",
            "Bucket By Amount:checkpoint",
            "Select Mid Columns",
        ]

class TestSwitchDefaultFallbackPipeline:
    def test_falls_back_to_default_case_when_no_case_matches(self, engine):
        result = _run(engine, "switch_default_fallback_pipeline.json")
        leaves = _leaves_by_node(result)

        # mean amount ~99.6 < 500, so the expression yields 'huge', which isn't in
        # cases=["tiny"] -> must route to default_case="unmatched"
        assert set(leaves) == {"6"}
        assert leaves["6"]["columns"] == ["customer", "amount", "quantity"]
        assert leaves["6"]["history"] == [
            "Fetch Data",
            "Select Columns",
            "Fill Missing (Mean)",
            "Bucket By Amount:checkpoint",
        ]

class TestUnionPipeline:
    def test_unions_two_branches_from_the_same_source(self, engine):
        result = _run(engine, "union_pipeline.json")
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
    @pytest.mark.parametrize("mock_path", sorted(MOCKS_DIR.glob("*.json")), ids=lambda p: p.name)
    def test_pipeline_completes_without_failing(self, engine, mock_path):
        result = _run(engine, mock_path.name)
        assert len(result["leaves"]) >= 1
