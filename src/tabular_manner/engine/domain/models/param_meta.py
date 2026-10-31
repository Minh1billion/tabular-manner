from typing import Any, Iterable

DTYPE_NAMES = (
    "Int8", "Int16", "Int32", "Int64",
    "UInt8", "UInt16", "UInt32", "UInt64",
    "Float32", "Float64",
    "Boolean", "String",
    "Date", "Datetime", "Time", "Duration",
)

def _column_meta(kind: str, dtype: str | None, scope: str | None) -> dict[str, Any]:
    meta: dict[str, Any] = {"kind": kind}
    if dtype:
        meta["dtype"] = dtype
    if scope:
        meta["scope"] = scope
    return meta

def column(dtype: str | None = None, scope: str | None = None) -> dict[str, Any]:
    return _column_meta("column", dtype, scope)

def columns(dtype: str | None = None, scope: str | None = None) -> dict[str, Any]:
    return _column_meta("columns", dtype, scope)

def enum(options: Iterable[str]) -> dict[str, Any]:
    return {"kind": "enum", "options": list(options)}

def number(minimum: float | None = None) -> dict[str, Any]:
    meta: dict[str, Any] = {"kind": "number"}
    if minimum is not None:
        meta["min"] = minimum
    return meta

def text() -> dict[str, Any]:
    return {"kind": "text"}

def mapping(key: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "map", "key": key, "value": value}

def value_like(source: str) -> dict[str, Any]:
    return {"kind": "value", "like": source}

def resource() -> dict[str, Any]:
    return {"kind": "resource"}
