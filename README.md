<img src="./logo.svg" width="64" height="64" alt="Tabular Hub" />

# Tabular Manner

An engine built for designing data processing workflows low-code platform using a graph-based model.

<p>
  <img src="https://img.shields.io/badge/Python-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Polars-CD792C?logo=polars&logoColor=white" alt="Polars" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
</p>

## Getting Started

A pipeline is a JSON graph: a list of `nodes` (each with an `id`, `type`, `name`, and `params`) connected by `connections` (`from` -> `to`). Below is `samples/json/basic_clean_pipeline.json`, a simple linear pipeline that fetches data, selects columns, fills missing values, then exports the result:

```json
{
  "name": "Basic Clean Pipeline",
  "nodes": [
    {
      "id": "1",
      "type": "fetch_internal",
      "name": "Fetch Data",
      "params": { "key": "raw" }
    },
    {
      "id": "2",
      "type": "select",
      "name": "Select Columns",
      "params": { "columns": ["customer", "amount", "quantity"] }
    },
    {
      "id": "3",
      "type": "fill_mean",
      "name": "Fill Missing (Mean)",
      "params": { "columns": ["amount", "quantity"] }
    },
    {
      "id": "4",
      "type": "push_internal",
      "name": "Export Result",
      "params": { "key": "cleaned" }
    }
  ],
  "connections": [
    { "from": "1", "to": "2" },
    { "from": "2", "to": "3" },
    { "from": "3", "to": "4" }
  ]
}
```

Run it with the built-in engine:

```python
from tabular_manner.engine import build_engine
import json

engine = build_engine()

with open("samples/json/basic_clean_pipeline.json") as f:
    spec = json.load(f)

for event in engine.execution.execute(spec=spec):
    print(event["event"], event.get("data", ""))
```

More graph patterns (branching, joins) are available under `samples/json/`.

## Architecture

The engine follows a hexagonal-style layout. `engine/` is the centralized
entry point - everything a consumer needs (`build_engine`, `Engine`,
`DataResource`, `Execution`, `NodeLibrary`) is importable from
`tabular_manner.engine` directly. The packages underneath it
(`application/`, `domain/`, `infrastructure/`) hold implementation details
and aren't meant to be imported from outside `engine/`.

```
src/tabular_manner/
  __init__.py          # re-exports the public engine API at the top level
  engine/
    __init__.py         # centralized entry point: Engine, build_engine, DataResource, Execution, NodeLibrary
    bootstrap.py          # wires the internal services together into an Engine
    api/                    # public-facing classes returned by build_engine
      data_resource.py
      execution.py
      node_library.py
    application/             # use-case/service layer (compiler, runtime, nodes, io, storage, ports)
    domain/                    # domain models (Plan, Operator, CustomNodeDefinition, ...)
    infrastructure/              # concrete adapters (local/S3 storage, file/database readers, node library repos)
```

**Public surface**

- `tabular_manner.build_engine(...)` / `tabular_manner.engine.build_engine(...)` - the
  only supported way to construct an `Engine`. It wires up storage, the node
  registry, and the sandboxed execution runtime, with sensible local-filesystem
  defaults.
- `Engine` - a frozen dataclass exposing `data_resource`, `node_library`,
  `execution`, `context_manager`, `registry`, and `sandbox`. In practice you'll
  mostly use `engine.data_resource`, `engine.node_library`, and
  `engine.execution`.
- `DataResource`, `Execution`, `NodeLibrary` (`engine/api/`) - the operations
  available on an `Engine` instance (import/list/get/delete resources, compile
  and run graphs, register/list custom nodes). Each method yields structured
  progress events (`{"event": ..., "ts": ..., ...}`) rather than returning a
  single value, so callers can stream status as work happens.

**Everything else is an implementation detail**

`application/`, `domain/`, and `infrastructure/` hold everything
`bootstrap.py` wires together - the graph compiler/parser/validator, the
node registry and sandbox, reader/writer factories, resource storage, and
the local/S3 adapters that implement them. There's nothing structurally
stopping you from importing them directly, but they aren't part of the
supported API and can change without notice - go through `engine/` instead.
If you find yourself reaching in here regularly, that's usually a sign
something should be exposed through `engine/api/` or a `build_engine(...)`
parameter instead.

**Extending the engine**

- Custom transform/action nodes: use `engine.node_library.register_transform(...)`
  or `engine.node_library.register_action(...)` - no need to touch the node
  registry directly.
- Alternate storage/readers/writers: `build_engine(...)` accepts
  `resource_storage_repository`, `node_library_repository`, `reader_factory`,
  and `writer_factory` overrides (e.g. swap in the S3-backed repositories from
  `infrastructure/` at the call site) without needing to reach into any other
  internals.

## Documentation

Full API and node reference: [minh1billion.github.io/tabular-manner](https://minh1billion.github.io/tabular-manner/)