from dataclasses import dataclass

import polars as pl

@dataclass(frozen=True)
class Schema:
    fields: dict[str, pl.DataType]

    def names(self) -> list[str]:
        return list(self.fields.keys())

    def get(self, name: str) -> pl.DataType | None:
        return self.fields.get(name)

    def to_polars(self) -> pl.LazyFrame:
        return pl.LazyFrame(schema=self.fields)

    def as_str_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.fields.items()}

    @classmethod
    def from_polars(cls, schema: pl.Schema) -> "Schema":
        return cls(dict(schema))

    @classmethod
    def from_declared(cls, declared: dict[str, str]) -> "Schema":
        fields: dict[str, pl.DataType] = {}
        for name, dtype_name in declared.items():
            dtype = getattr(pl, dtype_name, None)
            if not isinstance(dtype, type) or not issubclass(dtype, pl.DataType):
                raise ValueError(f"Unknown polars dtype '{dtype_name}' for column '{name}'")
            fields[name] = dtype
        return cls(fields)