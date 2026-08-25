# Tabular Manner

Tabular Manner is a graph-based engine for data processing workflows. A pipeline is described as a JSON graph of nodes and connections; the engine validates it, compiles it into an execution graph, and streams lifecycle events as it runs.

```
spec -> validate -> parse -> execute -> event stream
```

- **JSON graph spec** is handed to the **Validator + Parser**, which compiles the graph.
- The **Execution** engine traverses nodes and streams events (`node_completed` per node, `leaf_reached` per output branch).

## Overview

A pipeline is a named JSON document with two top-level arrays: `nodes` and `connections`. Each node wraps one registered node type; connections wire node outputs to node inputs, optionally through a named input slot.

**Nodes** — each entry has an `id`, a `type` naming a registered node, a display `name`, and a `params` object with the node's configuration.

**Connections** — each entry has a `from` id and a `to` id, and optionally `into` (which input slot to fill on a fan-in node such as `join`).

Any node with no incoming connection is treated as an entry point; a graph needs at least one. Execution starts at every entry point and fans out along the connections until every branch reaches a node with no outgoing connection, called a leaf.

Continue to [Getting started](getting-started.md) to run your first pipeline, or jump to [Writing a graph](writing-a-graph.md) for the full spec.
