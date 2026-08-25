import threading

from ...domain.models.operator import Operator

class NodeRegistry:
    _builtin_registry: dict[str, type[Operator]] = {}

    def __init__(self):
        self._dynamic_registry: dict[str, type[Operator]] = {}
        self._lock = threading.Lock()

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
        with self._lock:
            if key in self._builtin_registry or key in self._dynamic_registry:
                raise ValueError(f"Node type '{key}' is already registered")
            operator_cls.registry_key = key
            self._dynamic_registry[key] = operator_cls

    def unregister_dynamic(self, key: str) -> None:
        with self._lock:
            if key in self._builtin_registry:
                raise ValueError(f"Cannot unregister built-in node type '{key}'")
            if key not in self._dynamic_registry:
                raise KeyError(f"Unknown node type '{key}'")
            del self._dynamic_registry[key]

    def is_builtin(self, key: str) -> bool:
        return key in self._builtin_registry

    def get(self, key: str) -> type[Operator]:
        with self._lock:
            if key in self._dynamic_registry:
                return self._dynamic_registry[key]
        if key in self._builtin_registry:
            return self._builtin_registry[key]
        raise KeyError(f"Unknown node type '{key}'")

    def keys(self) -> list[str]:
        with self._lock:
            return [*self._builtin_registry, *self._dynamic_registry]

def _register_builtin_operators() -> None:
    from . import builtin  # noqa: F401

_register_builtin_operators()

class NodeRegistryProvider:
    DEFAULT_BUCKET = "default"

    def __init__(self):
        self._registries: dict[str, NodeRegistry] = {}
        self._lock = threading.Lock()

    def get(self, bucket: str | None = None) -> NodeRegistry:
        key = bucket or self.DEFAULT_BUCKET
        with self._lock:
            registry = self._registries.get(key)
            if registry is None:
                registry = NodeRegistry()
                self._registries[key] = registry
            return registry

    def buckets(self) -> list[str]:
        with self._lock:
            return sorted(self._registries)
