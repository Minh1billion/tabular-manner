# API reference

## Execution

Compiles a graph spec and runs it, or re-runs a graph already compiled in a previous call. Accessible as `engine.execution`.

### `execute(execution_id=None, spec=None)`

```
Iterator[dict] execute(execution_id: str | None, spec: dict | None)
```

Provide `spec` to validate, parse, and run a new graph in one call, or pass a previously returned `execution_id` to re-run an already-compiled graph against a fresh context. Exactly one of the two is required.

| Event | When |
|---|---|
| `validating` | Spec structure and node params are being checked. |
| `parsing` | Nodes and connections are compiled into an execution graph. |
| `compiled` | Carries the new `execution_id`, entry node ids, and node count. |
| `injecting_context` | Shared services (storage, readers, writers) are bound to nodes. |
| `running` | Traversal starts; carries `total_nodes`. |
| `node_started` / `node_completed` | Emitted for every node visited, in traversal order. |
| `leaf_reached` | Emitted once per branch with no outgoing connection; carries the resulting column list and step history. |
| `completed` | Final event; carries the `execution_id` and all reached leaves. |
| `failed` | Carries the error message, error type, and, for node failures, the offending `node_id` and `node_type`. |

### `validate(spec)`

```
Iterator[dict] validate(spec: dict)
```

Checks a spec against the registry and sandbox without compiling or running it. Yields `validating` followed by either `valid` or `failed`.

## DataResource

Manages the named internal resources that `fetch_internal` and `push_internal` nodes read from and write to. Accessible as `engine.data_resource`.

| Method | Parameters | Description |
|---|---|---|
| `import_source` | `key, source_kind, source_params, bucket=None, overwrite=False` | Reads from an external source (file, database, and so on) and saves the result under `key`. |
| `list` | `bucket=None, prefix=None, limit=None, offset=0` | Lists stored resource keys, optionally filtered by prefix and paged. |
| `get` | `key, bucket=None, limit=100, offset=0` | Returns schema, row count, and a page of rows for a stored resource. |
| `delete` | `key, bucket=None` | Removes a stored resource. |
| `exists` | `key, bucket=None` | Returns a plain boolean, not an event stream. |

Resources are scoped by an optional `bucket`, letting the same key coexist across separate namespaces.

## NodeLibrary

Registers custom node types on top of the built-in ones, so a graph can reference project-specific logic by name. Accessible as `engine.node_library`.

| Method | Parameters | Description |
|---|---|---|
| `register_transform` | `name, expression, description="", bucket=None` | Registers a reusable sandboxed expression as a new transform node type. |
| `unregister_node` | `name, bucket=None` | Removes a previously registered custom node type. Built-in types cannot be unregistered. |
| `get_node` | `name, bucket=None` | Returns the definition of one custom node type. |
| `describe_nodes` | `bucket=None` | Returns a descriptive summary of every node type available to the parser. |
| `list_nodes` | `bucket=None` | Returns built-in type keys alongside full definitions of custom types. |

Custom node types are looked up by the parser the same way built-in ones are, so once registered they can be used as any other `type` value in a graph spec.

!!! note
    Only expression-based custom transforms are supported. Registering a node type that calls an external service method (previously `register_action`) is not available in the current engine.
