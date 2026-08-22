import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed import generate_dataframe
from src.engine.bootstrap import build_engine
from src.engine.application.storage.resource_storage import ResourceStorage
from src.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

SAMPLES_DIR = PROJECT_ROOT / "samples" / "json"
STORAGE_ROOT = PROJECT_ROOT / ".tm" / "resource_storage"

_PREREQUISITE_PIPELINES = (
    "fanout_clean_pipeline.json",
    "switch_amount_bucket_pipeline.json",
)

def _seed_raw() -> None:
    repository = LocalResourceStorageRepository(root=str(STORAGE_ROOT))
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

    engine = build_engine(storage_root=str(STORAGE_ROOT))
    for name in _PREREQUISITE_PIPELINES:
        spec = json.loads((SAMPLES_DIR / name).read_text())
        events = list(engine.execution.execute(spec=spec))
        failed = [e for e in events if e["event"] == "failed"]
        assert not failed, f"prerequisite pipeline '{name}' failed while seeding: {failed}"

    yield