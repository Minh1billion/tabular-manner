import json
import sys

import pytest

from tabular_manner.engine.bootstrap import build_engine
from tabular_manner.engine.application.storage.resource_storage import ResourceStorage
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

from tests.support.paths import default_storage_root, find_repo_root, samples_dir

PROJECT_ROOT = find_repo_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))  # only needed for `scripts.seed` below

from scripts.seed import generate_dataframe

_PREREQUISITE_PIPELINES = (
    "fanout_clean_pipeline.json",
    "switch_amount_bucket_pipeline.json",
)

@pytest.fixture(scope="session")
def project_root():
    """Repo root. Change resolution logic in tests/support/paths.py, not here."""
    return PROJECT_ROOT

@pytest.fixture(scope="session")
def samples_path():
    """Directory holding sample pipeline JSON files."""
    return samples_dir()

@pytest.fixture(scope="session")
def storage_root():
    """Default local resource-storage root shared by the whole test session."""
    return default_storage_root()

@pytest.fixture
def engine(storage_root):
    """A fresh Engine wired to the shared storage root. Most tests just need this."""
    return build_engine(storage_root=str(storage_root))

@pytest.fixture
def load_spec(samples_path):
    """load_spec("some_pipeline.json") -> parsed graph spec dict."""
    def _load(name: str) -> dict:
        return json.loads((samples_path / name).read_text())
    return _load

def _seed_raw() -> None:
    repository = LocalResourceStorageRepository(root=str(default_storage_root()))
    resource_storage = ResourceStorage(repository=repository)
    df = generate_dataframe(n_rows=2000, null_ratio=0.1, seed=42)
    resource_storage.save("raw", df.lazy())

@pytest.fixture(scope="session", autouse=True)
def seeded_resource_storage():
    """Make `.tm/resource_storage` self-sufficient before any test runs.

    Seeds the "raw" resource and pre-runs the pipelines that other sample
    pipelines depend on, so the suite passes on a completely fresh checkout
    without requiring a prior manual `scripts/seed.py` / `scripts/mock.py` run.
    """
    _seed_raw()

    engine = build_engine(storage_root=str(default_storage_root()))
    for name in _PREREQUISITE_PIPELINES:
        spec = json.loads((samples_dir() / name).read_text())
        events = list(engine.execution.execute(spec=spec))
        failed = [e for e in events if e["event"] == "failed"]
        assert not failed, f"prerequisite pipeline '{name}' failed while seeding: {failed}"

    yield
