import pytest

from tabular_manner.engine.application.nodes.registry import NodeRegistry
from tabular_manner.engine.domain.models.operator import Operator

class _Dummy(Operator):
    pass

@pytest.fixture
def registry():
    return NodeRegistry()

class TestBuiltinKeys:
    def test_select_is_registered_as_builtin(self, registry):
        assert "select" in registry.keys()
        assert registry.is_builtin("select")

    def test_get_returns_operator_class(self, registry):
        assert registry.get("select").__name__ == "Select"

    def test_get_unknown_key_raises(self, registry):
        with pytest.raises(KeyError, match="Unknown node type"):
            registry.get("does_not_exist")

    def test_register_duplicate_builtin_key_raises(self, registry):
        with pytest.raises(ValueError, match="already registered"):
            NodeRegistry.register("select")(_Dummy)

class TestDynamicRegistration:
    def test_register_dynamic_adds_key(self, registry):
        registry.register_dynamic("dummy", _Dummy)
        assert "dummy" in registry.keys()
        assert not registry.is_builtin("dummy")

    def test_register_dynamic_duplicate_raises(self, registry):
        registry.register_dynamic("dummy", _Dummy)
        with pytest.raises(ValueError, match="already registered"):
            registry.register_dynamic("dummy", _Dummy)

    def test_unregister_dynamic_removes_key(self, registry):
        registry.register_dynamic("dummy", _Dummy)
        registry.unregister_dynamic("dummy")
        assert "dummy" not in registry.keys()

    def test_unregister_dynamic_unknown_key_raises(self, registry):
        with pytest.raises(KeyError):
            registry.unregister_dynamic("does_not_exist")

    def test_unregister_dynamic_builtin_raises(self, registry):
        with pytest.raises(ValueError, match="Cannot unregister built-in"):
            registry.unregister_dynamic("select")

    def test_dynamic_registration_is_isolated_per_instance(self):
        a = NodeRegistry()
        b = NodeRegistry()
        a.register_dynamic("dummy", _Dummy)

        assert "dummy" in a.keys()
        assert "dummy" not in b.keys()
        with pytest.raises(KeyError):
            b.get("dummy")