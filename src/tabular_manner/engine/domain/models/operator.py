from abc import ABC
from typing import Any, ClassVar

from .plan import Plan

TypeSpec = type | tuple[type, type]

class Operator(ABC):
    required: ClassVar[dict[str, TypeSpec]] = {}
    optional: ClassVar[dict[str, tuple[TypeSpec, Any]]] = {}
    context: ClassVar[tuple[str, ...]] = ()
    default_port: ClassVar[str] = "out"
    ports: ClassVar[tuple[str, ...] | None] = None
    fan_in: ClassVar[bool] = False
    in_ports: ClassVar[tuple[str, ...] | None] = None
    registry_key: ClassVar[str | None] = None

    def valid_ports(self) -> tuple[str, ...]:
        return self.ports if self.ports is not None else (self.default_port,)

    def __init__(self, name: str | None = None, sandbox: object | None = None, **params):
        self.name = name or self.type
        self.sandbox = sandbox
        self.params = params
        self.validate()

    @property
    def type(self) -> str:
        return self.__class__.__name__.lower()

    @staticmethod
    def _check_type(value: Any, spec: TypeSpec) -> bool:
        if isinstance(spec, tuple) and len(spec) == 2 and spec[0] is list:
            elem_type = spec[1]
            return isinstance(value, list) and all(isinstance(v, elem_type) for v in value)
        return isinstance(value, spec)

    @staticmethod
    def _type_name(spec: TypeSpec) -> str:
        if isinstance(spec, tuple) and len(spec) == 2 and spec[0] is list:
            return f"list[{spec[1].__name__}]"
        return spec.__name__

    def validate(self):
        for field_name, spec in self.required.items():
            if field_name not in self.params:
                raise ValueError(f"'{field_name}' is required")
            value = self.params[field_name]
            if not self._check_type(value, spec):
                raise TypeError(f"'{field_name}' must be of type {self._type_name(spec)}")
            setattr(self, field_name, value)

        for field_name, (spec, default) in self.optional.items():
            value = self.params.get(field_name, default)
            if value is not None and not self._check_type(value, spec):
                raise TypeError(f"'{field_name}' must be of type {self._type_name(spec)}")
            setattr(self, field_name, value)

    def bind(self, resources: dict[str, object]) -> None:
        for key in self.context:
            if key in resources:
                setattr(self, key, resources[key])

    def forward(self, plan: Plan) -> tuple[Plan, str]:
        raise NotImplementedError(f"'{self.type}' does not support single-input forward()")

    def forward_many(self, plans: list[Plan]) -> tuple[Plan, str]:
        raise NotImplementedError(f"'{self.type}' does not support multi-input forward_many()")