import re
from datetime import datetime, timezone

import polars as pl

from ...domain.models.custom_node import CustomNodeDefinition
from ...domain.models.operator import Operator
from .builtin.transform import Transform
from ..ports.node_library_repository import NodeLibraryRepository
from .registry import NodeRegistry, NodeRegistryProvider
from ..runtime.expression_compiler import ExpressionCompiler
from ..runtime.sandbox import Sandbox

def _build_operator_class(definition: CustomNodeDefinition) -> type[Operator]:
    expression = definition.expression

    class _CustomTransform(Transform):
        required = {"columns": (list, str)}

        def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
            return lf.with_columns(
                LibraryService.COMPILER.evaluate(expression, {"value": pl.col(c), "pl": pl}).alias(c)
                for c in self.columns
            )

    _CustomTransform.__name__ = definition.name
    _CustomTransform.__qualname__ = definition.name
    return _CustomTransform

class LibraryService:
    NAME_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
    TRANSFORM_ALLOWED_NAMES = frozenset({"value", "pl"})
    PROBE_COLUMN = "__probe__"
    COMPILER = ExpressionCompiler()

    def __init__(self, repository: NodeLibraryRepository, registry_provider: NodeRegistryProvider, sandbox: Sandbox):
        self._repository = repository
        self._registry_provider = registry_provider
        self._sandbox = sandbox

    def _validate_name(self, name: str, registry: NodeRegistry) -> None:
        if not name or not self.NAME_PATTERN.fullmatch(name):
            raise ValueError("'name' must be a non-empty identifier (letters, digits, underscore, not starting with a digit)")
        if name in registry.keys():
            raise ValueError(f"Node type '{name}' is already registered")

    def _persist_and_register(self, definition: CustomNodeDefinition, registry: NodeRegistry, bucket: str | None = None) -> CustomNodeDefinition:
        self._repository.save(definition, bucket=bucket)
        try:
            registry.register_dynamic(definition.name, _build_operator_class(definition))
        except Exception:
            self._repository.delete(definition.name, bucket=bucket)
            raise
        return definition

    def _ensure_registered(self, definition: CustomNodeDefinition, registry: NodeRegistry) -> None:
        if definition.name not in registry.keys():
            registry.register_dynamic(definition.name, _build_operator_class(definition))

    def register_transform(
        self, name: str, expression: str, description: str = "", bucket: str | None = None
    ) -> CustomNodeDefinition:
        registry = self._registry_provider.get(bucket)
        self._validate_name(name, registry)
        if not expression or not expression.strip():
            raise ValueError("'expression' must not be empty")

        self._sandbox.check_expression(expression, allowed_names=self.TRANSFORM_ALLOWED_NAMES)
        probe = self.COMPILER.evaluate(expression, {"value": pl.col(self.PROBE_COLUMN), "pl": pl})
        if not isinstance(probe, pl.Expr):
            raise TypeError("'expression' must evaluate to a polars Expr")

        definition = CustomNodeDefinition(
            name=name,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
            expression=expression,
        )
        return self._persist_and_register(definition, registry, bucket=bucket)

    def unregister_transform(self, name: str, bucket: str | None = None) -> None:
        registry = self._registry_provider.get(bucket)
        if registry.is_builtin(name):
            raise ValueError(f"Cannot unregister built-in node type '{name}'")

        definition = self._repository.get(name, bucket=bucket)
        self._ensure_registered(definition, registry)
        registry.unregister_dynamic(definition.name)
        self._repository.delete(definition.name, bucket=bucket)

    def get_transform(self, name: str, bucket: str | None = None) -> CustomNodeDefinition:
        return self._repository.get(name, bucket=bucket)

    def list_transforms(self, bucket: str | None = None) -> list[CustomNodeDefinition]:
        return self._repository.list(bucket=bucket)

    def builtin_keys(self) -> list[str]:
        registry = self._registry_provider.get()
        return sorted(key for key in registry.keys() if registry.is_builtin(key))

    def describe_operator(self, operator_cls: type[Operator]) -> dict:
        return {
            "type": operator_cls.registry_key or operator_cls.__name__.lower(),
            "required": {k: Operator._type_name(v) for k, v in operator_cls.required.items()},
            "optional": {k: Operator._type_name(v[0]) for k, v in operator_cls.optional.items()},
            "ports_out": list(operator_cls.ports) if operator_cls.ports is not None else [operator_cls.default_port],
            "fan_in": operator_cls.fan_in,
            "in_ports": list(operator_cls.in_ports) if operator_cls.in_ports is not None else None,
        }

    def describe_nodes(self, bucket: str | None = None) -> dict:
        registry = self._registry_provider.get(bucket)
        builtin = [self.describe_operator(registry.get(key)) for key in self.builtin_keys()]
        custom_definitions = self._repository.list(bucket=bucket)
        for definition in custom_definitions:
            self._ensure_registered(definition, registry)
        custom = [self.describe_operator(registry.get(d.name)) for d in custom_definitions]
        return {"builtin": builtin, "custom": custom}

    def load_persisted(self, bucket: str | None = None) -> None:
        registry = self._registry_provider.get(bucket)
        for definition in self._repository.list(bucket=bucket):
            if definition.name in registry.keys():
                continue
            registry.register_dynamic(definition.name, _build_operator_class(definition))
