import json
import threading

import polars as pl
import pytest

from tabular_manner.engine.application.nodes.builtin.control import If, Switch
from tabular_manner.engine.domain.models.plan import Plan

def _lf_with_probe(counter: dict, lock: threading.Lock) -> pl.LazyFrame:
    def _touch(df: pl.DataFrame) -> pl.DataFrame:
        with lock:
            counter["n"] += 1
        return df

    return pl.LazyFrame({"amount": [100.0, 200.0, 300.0]}).map_batches(
        _touch, schema={"amount": pl.Float64}
    )

class TestControlCheckpoint:
    def test_switch_forward_commits_checkpoint_step(self, engine):
        material_buffer = engine.context_manager.get("material_buffer")

        node = Switch(
            name="Bucket",
            expression="pl.when(df.amount.mean() >= 150).then(pl.lit('high')).otherwise(pl.lit('low'))",
            cases=["high", "low"],
        )
        node.bind({"material_buffer": material_buffer})

        plan = Plan(
            handle=pl.LazyFrame({"amount": [100.0, 200.0, 300.0]}),
            meta={"execution_id": "test-exec"},
        )
        result_plan, port = node.forward(plan)

        assert port == "high"
        assert result_plan.history[-1] == "Bucket:checkpoint"
        # downstream plan should now be backed by an already-materialized frame
        assert result_plan.handle.collect().to_dict(as_series=False) == {
            "amount": [100.0, 200.0, 300.0]
        }

    def test_repeated_switch_on_same_upstream_does_not_recollect(self, engine):
        material_buffer = engine.context_manager.get("material_buffer")

        counter = {"n": 0}
        lock = threading.Lock()
        upstream = _lf_with_probe(counter, lock)

        base_plan = Plan(handle=upstream, meta={"execution_id": "test-exec"}).commit(
            upstream, step="shared_upstream"
        )

        switch_a = Switch(
            name="A",
            expression="pl.when(df.amount.mean() >= 150).then(pl.lit('high')).otherwise(pl.lit('low'))",
            cases=["high", "low"],
        )
        switch_a.bind({"material_buffer": material_buffer})

        checkpoint_plan, _ = switch_a.forward(base_plan)
        assert counter["n"] == 1

        switch_a.forward(base_plan)
        assert counter["n"] == 1

    def test_if_node_checkpoints_too(self, engine):
        material_buffer = engine.context_manager.get("material_buffer")

        node = If(name="HasRows", expression="df.amount.len() > 0")
        node.bind({"material_buffer": material_buffer})

        plan = Plan(handle=pl.LazyFrame({"amount": [1.0]}), meta={"execution_id": "test-exec"})
        result_plan, port = node.forward(plan)

        assert port == "true"
        assert result_plan.history[-1] == "HasRows:checkpoint"

class TestExecutionBufferLifecycle:
    @pytest.mark.parametrize(
        "mock_name",
        ["switch_amount_bucket_pipeline.json", "switch_default_fallback_pipeline.json"],
    )
    def test_buffer_cleared_after_successful_execution(self, engine, load_spec, mock_name):
        material_buffer = engine.context_manager.get("material_buffer")
        spec = load_spec(mock_name)

        assert len(material_buffer) == 0

        saw_entries_mid_run = False
        for event in engine.execution.execute(spec=spec):
            assert event["event"] != "failed", event.get("error")
            if len(material_buffer) > 0:
                saw_entries_mid_run = True

        assert saw_entries_mid_run, "expected the switch checkpoint to populate the buffer mid-run"
        assert len(material_buffer) == 0, "buffer should be cleared once execution completes"

    def test_buffer_cleared_on_failed_execution(self, engine):
        material_buffer = engine.context_manager.get("material_buffer")

        bad_spec = {"nodes": [], "connections": []}  # invalid: no entry node
        for event in engine.execution.execute(spec=bad_spec):
            pass

        assert len(material_buffer) == 0

    def test_no_accumulation_across_repeated_executions(self, engine, load_spec):
        material_buffer = engine.context_manager.get("material_buffer")
        spec = load_spec("switch_amount_bucket_pipeline.json")

        for _ in range(5):
            for event in engine.execution.execute(spec=spec):
                assert event["event"] != "failed", event.get("error")

        assert len(material_buffer) == 0

    def test_all_mock_pipelines_still_run_successfully(self, engine, samples_path):
        for mock_path in sorted(samples_path.glob("*.json")):
            spec = json.loads(mock_path.read_text())
            events = list(engine.execution.execute(spec=spec))
            failed = [e for e in events if e["event"] == "failed"]
            assert not failed, f"{mock_path.name} failed: {failed}"
            completed = [e for e in events if e["event"] == "completed"]
            assert completed, f"{mock_path.name} never completed"
