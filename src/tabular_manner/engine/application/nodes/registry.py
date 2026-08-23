from ...domain.models.operator import Operator

class NodeRegistry:
    _builtin_registry: dict[str, type[Operator]] = {}

    def __init__(self):
        self._dynamic_registry: dict[str, type[Operator]] = {}

    @classmethod
    def register(cls, key: str):
        def wrapper(operator_cls: type[Operator]):
            if key in cls._builtin_registry:
                raise ValueError(f"Node type '{key}' is already registered")
            operator_cls.registry_key = key
            cls._builtin_registry[key] = operator_cls
            return operator_cls
        return wrapper

    def register_dynamic(self, key: str, operator_cls: type[Operator]) -> None:
        if key in self._builtin_registry or key in self._dynamic_registry:
            raise ValueError(f"Node type '{key}' is already registered")
        operator_cls.registry_key = key
        self._dynamic_registry[key] = operator_cls

    def unregister_dynamic(self, key: str) -> None:
        if key in self._builtin_registry:
            raise ValueError(f"Cannot unregister built-in node type '{key}'")
        if key not in self._dynamic_registry:
            raise KeyError(f"Unknown node type '{key}'")
        del self._dynamic_registry[key]

    def is_builtin(self, key: str) -> bool:
        return key in self._builtin_registry

    def get(self, key: str) -> type[Operator]:
        if key in self._dynamic_registry:
            return self._dynamic_registry[key]
        if key in self._builtin_registry:
            return self._builtin_registry[key]
        raise KeyError(f"Unknown node type '{key}'")

    def keys(self) -> list[str]:
        return [*self._builtin_registry, *self._dynamic_registry]

def _register_builtin_operators() -> None:
    from . import builtin  # noqa: F401  (triggers registration side-effects)

_register_builtin_operators()