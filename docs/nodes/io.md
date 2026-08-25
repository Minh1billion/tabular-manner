# Source and sink nodes

Sources start a branch by reading data in; sinks end a branch by writing data out. Both types read and write lazily.

## `fetch_internal` — source

| Param | Type | Default | Notes |
|---|---|---|---|
| `key` | string | required | Resource key previously saved via `push_internal` or `import_source`. |
| `bucket` | string | none | Optional storage namespace. |

## `fetch_csv` — source

| Param | Type | Default |
|---|---|---|
| `path` | string | required |
| `separator` | string | `","` |
| `has_header` | bool | `true` |
| `encoding` | string | `"utf8"` |

## `fetch_parquet` — source

| Param | Type | Default |
|---|---|---|
| `path` | string | required |
| `columns` | list of string | none (all columns) |
| `n_rows` | integer | none (all rows) |

## `fetch_arrow` — source

| Param | Type | Default |
|---|---|---|
| `path` | string | required |

## `fetch_s3` — source

| Param | Type | Default |
|---|---|---|
| `bucket` | string | required |
| `key` | string | required |
| `format` | string | `"parquet"` (or `"csv"`) |
| `region` | string | none |
| `storage_options` | object | none |

## `fetch_postgres` — source

| Param | Type | Default |
|---|---|---|
| `dsn` | string | required |
| `table` | string | required |
| `query` | string | none (reads whole table) |
| `partition_on` | string | none |
| `partition_num` | integer | none |

## `push_internal` — sink

| Param | Type | Default |
|---|---|---|
| `key` | string | required |
| `bucket` | string | none |

## `push_csv` / `push_parquet` / `push_arrow` — sink

| Param | Type | Default | Applies to |
|---|---|---|---|
| `path` | string | required | all three |
| `separator` | string | `","` | `push_csv` only |
| `include_header` | bool | `true` | `push_csv` only |

## `push_postgres` — sink

| Param | Type | Default |
|---|---|---|
| `dsn` | string | required |
| `table` | string | required |
| `if_table_exists` | string | `"append"` |
