import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.bootstrap import Engine, build_engine

def run_mock(execution, pipeline_path: Path) -> None:
    print(f"\n{'=' * 60}")
    print(f"Running: {pipeline_path.name}")
    print(f"{'=' * 60}")

    try:
        spec = json.loads(pipeline_path.read_text())
    except json.JSONDecodeError as e:
        print(f"[FAIL] Invalid JSON: {e}")
        return

    result = None
    for event in execution.execute(spec=spec):
        name = event["event"]
        if name == "failed":
            print(f"[FAIL] {event['error']}")
            return
        if name == "node_completed":
            print(f"  ... node '{event['node_id']}' done ({event['processed']}/{event['total']})")
        elif name == "leaf_reached":
            print(f"  --- Branch ended at node '{event['node_id']}' ---")
            print(f"  History: {' -> '.join(event['history']) or '(no steps recorded)'}")
            print(f"  Columns: {event['columns']}")
        elif name == "completed":
            result = event["data"]

    if result is None:
        print("[FAIL] Execution did not complete")
        return

    print(f"\n[OK] Pipeline: {spec.get('name', pipeline_path.stem)}")
    print(f"     Branches: {len(result['leaves'])}")

def main() -> None:
    samples_dir = project_root / "samples" / "json"
    if not samples_dir.exists():
        print(f"No samples directory found at {samples_dir}")
        return

    pipeline_paths = sorted(samples_dir.glob("*.json"))
    if not pipeline_paths:
        print(f"No pipeline JSON files found in {samples_dir}")
        return

    engine: Engine = build_engine(storage_root=str(project_root / ".tm" / "resource_storage"))
    for pipeline_path in pipeline_paths:
        run_mock(engine.execution, pipeline_path)


if __name__ == "__main__":
    main()