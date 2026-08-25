# Getting started

The engine is assembled once with `build_engine()`, which wires together storage, the node registry, and the execution runtime into a single `Engine` object.

```python
from tabular_manner.engine.bootstrap import build_engine
import json

engine = build_engine()

# a pipeline is just a JSON graph of nodes and connections
with open("pipeline.json") as f:
    spec = json.load(f)

for event in engine.execution.execute(spec=spec):
    print(event["event"], event.get("data", ""))
```

Every call on the engine's APIs returns an iterator of event dictionaries rather than a single value. Each event has an `event` name and a `ts` timestamp; the terminal event is either `completed` (with a `data` payload) or `failed` (with an `error` message). This gives callers a consistent, streamable shape across validation, execution, resource management, and node registration.

## The Engine object

| Attribute | Type | Purpose |
|---|---|---|
| `execution` | `Execution` | Validate and run pipeline graphs. |
| `data_resource` | `DataResource` | Import, list, read, and remove named internal resources. |
| `node_library` | `NodeLibrary` | Register and inspect custom node types. |
| `registry` | `NodeRegistry` | The set of node types available to the parser, built-in and custom. |
| `context_manager` | `ContextManager` | Holds shared runtime services (storage, readers, writers) injected into nodes. |
| `sandbox` | `Sandbox` | Restricts what expressions are allowed to do. |
