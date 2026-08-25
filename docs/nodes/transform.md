# Transform nodes

Single-input, single-output nodes that reshape the data passing through a branch. Each takes one input and produces one output.

## `select`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Keeps only the given columns, in order. |

## `drop`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Removes the given columns. |

## `limit`

| Param | Type | Default | Notes |
|---|---|---|---|
| `n` | integer | required | Keeps at most the first `n` rows. |

## `head`

| Param | Type | Default | Notes |
|---|---|---|---|
| `n` | integer | required | Keeps the first `n` rows. |

## `tail`

| Param | Type | Default | Notes |
|---|---|---|---|
| `n` | integer | required | Keeps the last `n` rows. |

## `explode`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Explodes list-typed columns into multiple rows, one per element. |

## `group_by`

| Param | Type | Default | Notes |
|---|---|---|---|
| `by` | list of string | required | Columns to group rows by. |
| `aggregations` | object of string to string | required | Maps a column to one of `sum`, `mean`, `min`, `max`, `count`, `median`, `std`, `first`, `last`. |

## `log`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Columns to apply a logarithm to. |
| `base` | float | none (natural log) | Log base. Uses the natural log if omitted. |

## `zscore_normalize`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Rescales the given columns to zero mean and unit standard deviation. |

## `minmax_normalize`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Rescales the given columns to the [0, 1] range based on their min and max. |

## `fill_mean`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Fills nulls in the given columns with each column's mean. |

## `fill_null`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | required | Columns to fill. |
| `value` | any | required | Fixed value used to fill nulls in the given columns. |

## `drop_nulls`

| Param | Type | Default | Notes |
|---|---|---|---|
| `columns` | list of string | none (any column) | Drops rows with a null in any of the given columns, or any column if omitted. |

## `drop_duplicates`

| Param | Type | Default | Notes |
|---|---|---|---|
| `subset` | list of string | none (all columns) | Scopes duplicate detection to a subset of columns. |
| `keep` | string | `"first"` | One of `"first"`, `"last"`, `"any"`, `"none"`. |

## `rename`

| Param | Type | Default | Notes |
|---|---|---|---|
| `mapping` | object of string to string | required | Renames columns from old name to new name. |

## `sort`

| Param | Type | Default | Notes |
|---|---|---|---|
| `by` | list of string | required | Columns to sort rows by. |
| `descending` | bool | `false` | Sorts in descending order when true. |

## `cast`

| Param | Type | Default | Notes |
|---|---|---|---|
| `types` | object of string to string | required | Casts columns to the named Polars dtype, for example `Int64` or `Float64`. |

## `filter`

| Param | Type | Default | Notes |
|---|---|---|---|
| `expression` | string | required | Keeps rows where the sandboxed expression evaluates to true. |

## `derive`

| Param | Type | Default | Notes |
|---|---|---|---|
| `expression` | string | required | Sandboxed expression producing the column's value. |
| `column` | string | required | Adds or replaces this column with the result of `expression`. |

See [Expressions](../writing-a-graph.md#expressions) for what `filter` and `derive` accept in `expression`.
