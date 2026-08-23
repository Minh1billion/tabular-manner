import re
from datetime import datetime, timezone

import polars as pl

from ...domain.models.custom_node import CustomNodeDefinition
from ...domain.models.operator import Operator
from ...domain.models.plan import Plan
from .builtin.transform import Transform
from ..ports.node_library_repository import NodeLibraryRepository
from .registry import NodeRegistry
from ..runtime.expression_compiler import ExpressionCompiler
from ..runtime.sandbox import Sandbox

_NAME_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_TRANSFORM_ALLOWED_NAMES = frozenset({"value", "pl"})
_PROBE_COLUMN = "__probe__"
_COMPILER = ExpressionCompiler()

def _build_transform_operator(definition: CustomNodeDefinition) -> type[Operator]:
    expression = definition.expression

    class _CustomTransform(Transform):
        required = {"columns": (list, str)}

        def _apply(self, lf: pl.LazyFrame) -> pl.LazyFrame:
            return lf.with_columns(
                _COMPILER.evaluate(expression, {"value": pl.col(c), "pl": pl}).alias(c)
                for c in self.columns
            )

    _CustomTransform.__name__ = definition.name
    _CustomTransform.__qualname__ = definition.name
    return _CustomTransform

def _build_action_operator(definition: CustomNodeDefinition) -> type[Operator]:
    service_name = definition.service
    method_name = definition.method
    handle_param = definition.handle_param

    class _CustomAction(Operator):
        context = (service_name,)

        def validate(self):
            super().validate()
            if handle_param and handle_param in self.params:
                raise ValueError(
                    f"Node param '{handle_param}' collides with 'handle_param' of custom action "
                    f"'{definition.name}'; rename the node param or choose a different handle_param"
                )

        def forward(self, plan: Plan) -> tuple[Plan, str]:
            service = getattr(self, service_name)
            bound_method = getattr(service, method_name)

            call_kwargs = dict(self.params)
            if handle_param:
                call_kwargs[handle_param] = plan.handle

            result = bound_method(**call_kwargs)
            if isinstance(result, pl.LazyFrame):
                return plan.commit(result, step=self.name), self.default_port
            return plan, self.default_port

    _CustomAction.__name__ = definition.name
    _CustomAction.__qualname__ = definition.name
    return _CustomAction

def _build_operator_class(definition: CustomNodeDefinition) -> type[Operator]:
    if definition.kind == "transform":
        return _build_transform_operator(definition)
    if definition.kind == "action":
        return _build_action_operator(definition)
    raise ValueError(f"Unknown custom node kind '{definition.kind}'")

class LibraryService:
    def __init__(self, repository: NodeLibraryRepository, registry: NodeRegistry, sandbox: Sandbox):
        self._repository = repository
        self._registry = registry
        self._sandbox = sandbox

    def _validate_name(self, name: str) -> None:
        if not name or not _NAME_PATTERN.fullmatch(name):
            raise ValueError("'name' must be a non-empty identifier (letters, digits, underscore, not starting with a digit)")
        if name in self._registry.keys():
            raise ValueError(f"Node type '{name}' is already registered")

    def _persist_and_register(self, definition: CustomNodeDefinition, bucket: str | None = None) -> CustomNodeDefinition:
        self._repository.save(definition, bucket=bucket)
        try:
            self._registry.register_dynamic(definition.name, _build_operator_class(definition))
        except Exception:
            self._repository.delete(definition.name, bucket=bucket)
            raise
        return definition

    def _ensure_registered(self, definition: CustomNodeDefinition) -> None:
        if definition.name not in self._registry.keys():
            self._registry.register_dynamic(definition.name, _build_operator_class(definition))

    def register_transform(
        self, name: str, expression: str, description: str = "", bucket: str | None = None
    ) -> CustomNodeDefinition:
        self._validate_name(name)
        if not expression or not expression.strip():
            raise ValueError("'expression' must not be empty")

        self._sandbox.check_expression(expression, allowed_names=_TRANSFORM_ALLOWED_NAMES)
        probe = _COMPILER.evaluate(expression, {"value": pl.col(_PROBE_COLUMN), "pl": pl})
        if not isinstance(probe, pl.Expr):
            raise TypeError("'expression' must evaluate to a polars Expr")

        definition = CustomNodeDefinition(
            name=name,
            kind="transform",
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
            expression=expression,
        )
        return self._persist_and_register(definition, bucket=bucket)

    def register_action(
        self,
        name: str,
        service: str,
        method: str,
        description: str = "",
        handle_param: str | None = None,
        bucket: str | None = None,
    ) -> CustomNodeDefinition:
        self._validate_name(name)

        self._sandbox.check_service_call(service, method)
        if handle_param is not None and not handle_param.strip():
            raise ValueError("'handle_param' must not be empty when provided")

        definition = CustomNodeDefinition(
            name=name,
            kind="action",
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
            service=service,
            method=method,
            handle_param=handle_param,
        )
        return self._persist_and_register(definition, bucket=bucket)

    def unregister_transform(self, name: str, bucket: str | None = None) -> None:
        if self._registry.is_builtin(name):
            raise ValueError(f"Cannot unregister built-in node type '{name}'")

        definition = self._repository.get(name, bucket=bucket)
        self._ensure_registered(definition)
        self._registry.unregister_dynamic(definition.name)
        self._repository.delete(definition.name, bucket=bucket)

    def get_transform(self, name: str, bucket: str | None = None) -> CustomNodeDefinition:
        return self._repository.get(name, bucket=bucket)

    def list_transforms(self, bucket: str | None = None) -> list[CustomNodeDefinition]:
        return self._repository.list(bucket=bucket)

    def builtin_keys(self) -> list[str]:
        return sorted(key for key in self._registry.keys() if self._registry.is_builtin(key))

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
        builtin = [self.describe_operator(self._registry.get(key)) for key in self.builtin_keys()]
        custom_definitions = self._repository.list(bucket=bucket)
        for definition in custom_definitions:
            self._ensure_registered(definition)
        custom = [self.describe_operator(self._registry.get(d.name)) for d in custom_definitions]
        return {"builtin": builtin, "custom": custom}

    def load_persisted(self, bucket: str | None = None) -> None:
        for definition in self._repository.list(bucket=bucket):
            if definition.name in self._registry.keys():
                continue
            self._registry.register_dynamic(definition.name, _build_operator_class(definition))