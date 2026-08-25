# Merge nodes

Fan-in nodes that wait for every incoming branch before producing a single output.

## `union`

| Param | Type | Default | Notes |
|---|---|---|---|
| `how` | string | `"vertical_relaxed"` | Stacks any number of incoming branches on the default port. |

## `join`

| Param | Type | Default | Notes |
|---|---|---|---|
| `on` | list of string | required | Join key columns. |
| `how` | string | `"inner"` | Accepts exactly two inputs, tagged `left` and `right` via each connection's `into` field. |
