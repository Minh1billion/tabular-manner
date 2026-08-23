import sys
import threading
import time
from pathlib import Path

import polars as pl
import pytest

from tabular_manner.engine.application.runtime.material_buffer import MaterialBuffer

def _counting_lf(counter: dict, lock: threading.Lock, delay: float = 0.05) -> pl.LazyFrame:
    def _touch(df: pl.DataFrame) -> pl.DataFrame:
        with lock:
            counter["n"] += 1
        time.sleep(delay)
        return df

    return pl.LazyFrame({"a": [1, 2, 3]}).map_batches(_touch, schema={"a": pl.Int64})

class TestMaterialBufferBasics:
    def test_returns_correct_data(self):
        buf = MaterialBuffer()
        lf = pl.LazyFrame({"a": [1, 2, 3]})
        df = buf.get_or_materialize(("e", 1, 1), lf)
        assert df.to_dict(as_series=False) == {"a": [1, 2, 3]}

    def test_repeated_calls_same_key_collect_once(self):
        buf = MaterialBuffer()
        counter = {"n": 0}
        lock = threading.Lock()
        key = ("exec-1", 111, hash(("a", "b")))

        for _ in range(5):
            buf.get_or_materialize(key, _counting_lf(counter, lock))

        assert counter["n"] == 1

    def test_different_keys_collect_independently(self):
        buf = MaterialBuffer()
        counter = {"n": 0}
        lock = threading.Lock()

        buf.get_or_materialize(("e", 1, 1), _counting_lf(counter, lock))
        buf.get_or_materialize(("e", 2, 1), _counting_lf(counter, lock))
        buf.get_or_materialize(("e", 1, 2), _counting_lf(counter, lock))  # different history hash

        assert counter["n"] == 3

    def test_max_entries_must_be_positive(self):
        with pytest.raises(ValueError):
            MaterialBuffer(max_entries=0)

class TestMaterialBufferEviction:
    def test_lru_evicts_oldest_entry(self):
        buf = MaterialBuffer(max_entries=2)
        buf.get_or_materialize(("e", 1, 1), pl.LazyFrame({"a": [1]}))
        buf.get_or_materialize(("e", 2, 1), pl.LazyFrame({"a": [2]}))
        buf.get_or_materialize(("e", 3, 1), pl.LazyFrame({"a": [3]}))

        assert len(buf) == 2

    def test_lru_access_refreshes_recency(self):
        buf = MaterialBuffer(max_entries=2)
        counter = {"n": 0}
        lock = threading.Lock()

        k1, k2, k3 = ("e", 1, 1), ("e", 2, 1), ("e", 3, 1)
        buf.get_or_materialize(k1, _counting_lf(counter, lock))
        buf.get_or_materialize(k2, _counting_lf(counter, lock))

        # touch k1 again so k2 becomes the least-recently-used entry
        buf.get_or_materialize(k1, _counting_lf(counter, lock))
        assert counter["n"] == 2  # k1 was still cached, no re-collect

        buf.get_or_materialize(k3, _counting_lf(counter, lock))  # should evict k2, not k1
        assert len(buf) == 2

        counter["n"] = 0
        buf.get_or_materialize(k1, _counting_lf(counter, lock))
        assert counter["n"] == 0, "k1 should still be cached (was most recently used)"

        buf.get_or_materialize(k2, _counting_lf(counter, lock))
        assert counter["n"] == 1, "k2 should have been evicted and re-collected"

class TestMaterialBufferConcurrency:
    def test_concurrent_calls_same_key_single_flight(self):
        buf = MaterialBuffer()
        counter = {"n": 0}
        lock = threading.Lock()
        key = ("exec-1", 222, hash(("x",)))

        def worker():
            buf.get_or_materialize(key, _counting_lf(counter, lock))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert counter["n"] == 1

    def test_concurrent_calls_different_keys_run_in_parallel(self):
        buf = MaterialBuffer(max_entries=100)
        counter = {"n": 0}
        lock = threading.Lock()

        def worker(i):
            buf.get_or_materialize((f"exec-{i}", i, 1), _counting_lf(counter, lock, delay=0.05))

        start = time.monotonic()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        elapsed = time.monotonic() - start

        assert counter["n"] == 8
        # if calls serialized behind a single global lock this would take ~8*0.05s;
        # parallel execution should stay well under that.
        assert elapsed < 0.3, f"expected parallel execution, took {elapsed:.2f}s"

class TestMaterialBufferClear:
    def test_clear_scope_only_drops_matching_execution(self):
        buf = MaterialBuffer(max_entries=10)
        buf.get_or_materialize(("exec-A", 1, 1), pl.LazyFrame({"a": [1]}))
        buf.get_or_materialize(("exec-B", 1, 1), pl.LazyFrame({"a": [1]}))

        buf.clear(scope="exec-A")

        assert len(buf) == 1

    def test_clear_no_scope_drops_everything(self):
        buf = MaterialBuffer(max_entries=10)
        buf.get_or_materialize(("exec-A", 1, 1), pl.LazyFrame({"a": [1]}))
        buf.get_or_materialize(("exec-B", 1, 1), pl.LazyFrame({"a": [1]}))

        buf.clear()

        assert len(buf) == 0
