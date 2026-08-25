# Writing a graph

A graph spec has a name, a flat list of nodes, and a flat list of connections between them.

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
      "params": { "columns": ["customer", "amount"] }
    },
    {
      "id": "3",
      "type": "push_internal",
      "name": "Export Result",
      "params": { "key": "cleaned" }
    }
  ],
  "connections": [
    { "from": "1", "to": "2" },
    { "from": "2", "to": "3" }
  ]
}
```

## Node fields

| Field | Description |
|---|---|
| `id` | Unique string id, referenced by connections. |
| `type` | Key of a registered node type, built-in or custom. |
| `name` | Display label, recorded in each branch's step history. |
| `params` | Node-specific configuration object, validated against that node type's required and optional fields. |

## Connection fields

| Field | Description |
|---|---|
| `from` / `to` | Node ids being connected. |
| `into` | Input slot to fill on the target node. Required for fan-in nodes with named inputs, such as `join`'s `left` and `right`. |

!!! note "Entry points"
    Any node with no incoming connection starts a branch when the graph runs. A graph must have at least one; a graph with none fails validation.

## Ports and merging

Every built-in node has a single output port, so connections never need to pick a port on the way out. A node's output can still feed more than one connection — that's how a branch fans out to several downstream nodes.

Fan-in nodes work the other way: instead of choosing an output port, incoming connections choose an input slot. `union` accepts any number of branches on the default port and concatenates them. `join` requires exactly two, matched to its `left` and `right` input slots via each connection's `into` field.

## Expressions

The `expression` param used by `filter` and `derive` is not arbitrary Python. It is parsed and checked against a small allow-list before it ever runs.

| Allowed | Example |
|---|---|
| Column reference | `df.amount` |
| Column functions | `pl.col("amount")`, `pl.lit(1)` |
| Conditional expression | `pl.when(df.amount >= 150).then(pl.lit("high")).otherwise(pl.lit("low"))` |
| Arithmetic | `df.amount * df.quantity` |
| Comparisons | `df.amount >= 100` |
| Boolean logic | `df.amount > 0 and df.quantity > 0` |
| Method calls on columns | `df.amount.mean()` |

Anything outside this set — imports, arbitrary function calls, attribute access on anything other than `df` or a narrow set of `pl` helpers — is rejected before the graph runs rather than at data time.

`register_transform` (see [NodeLibrary](api-reference.md#nodelibrary)) uses the same sandbox with a `value` identifier in place of `df`, since a registered transform applies its expression per target column rather than against the whole row.

## Common patterns

A few small shapes cover most graphs: a straight line, a fan-out, and a merge.

### Fan-out to two sinks

```json
// a node's output can feed more than one connection
{ "from": "3", "to": "4" }
{ "from": "3", "to": "5" }
```

### Joining two branches

```json
{
  "id": "3", "type": "join", "name": "Join Customers With Amounts",
  "params": { "on": ["customer"], "how": "inner" }
}

// connections tag each side via "into"
{ "from": "1", "to": "3", "into": "left" }
{ "from": "2", "to": "3", "into": "right" }
```
