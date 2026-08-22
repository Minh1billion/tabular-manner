import threading
from collections import OrderedDict

import polars as pl

class MaterialBuffer:
    def __init__(self, max_entries: int = 64):
        if max_entries < 1:
            raise ValueError("'max_entries' must be >= 1")
        self._max_entries = max_entries
        self._store: OrderedDict[tuple, pl.DataFrame] = OrderedDict()
        self._lock = threading.RLock()
        self._key_locks: dict[tuple, threading.Lock] = {}

    def get_or_materialize(
        self, key: tuple, lf: pl.LazyFrame, *, engine: str = "streaming"
    ) -> pl.DataFrame:
        with self._lock:
            cached = self._store.get(key)
            if cached is not None:
                self._store.move_to_end(key)
                return cached
            key_lock = self._key_locks.setdefault(key, threading.Lock())

        with key_lock:
            with self._lock:
                cached = self._store.get(key)
                if cached is not None:
                    self._store.move_to_end(key)
                    return cached

            materialized = lf.collect(engine=engine)

            with self._lock:
                self._store[key] = materialized
                self._store.move_to_end(key)
                self._evict_locked()
                self._key_locks.pop(key, None)
                return self._store[key]

    def clear(self, scope: object | None = None) -> None:
        with self._lock:
            if scope is None:
                self._store.clear()
                return
            for key in [k for k in self._store if k[0] == scope]:
                del self._store[key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def _evict_locked(self) -> None:
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)