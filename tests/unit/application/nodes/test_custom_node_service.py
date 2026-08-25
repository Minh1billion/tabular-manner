import pytest

from tabular_manner.engine.application.nodes.custom_node_service import LibraryService, _build_operator_class
from tabular_manner.engine.application.nodes.registry import NodeRegistryProvider
from tabular_manner.engine.application.runtime.sandbox import Sandbox
from tabular_manner.engine.infrastructure.node_library.local_node_library_repository import LocalNodeLibraryRepository

@pytest.fixture
def repository(tmp_path):
    return LocalNodeLibraryRepository(root=str(tmp_path / ".node_library"))

@pytest.fixture
def registry_provider():
    return NodeRegistryProvider()

@pytest.fixture
def registry(registry_provider):
    return registry_provider.get()

@pytest.fixture
def service(repository, registry_provider):
    return LibraryService(repository=repository, registry_provider=registry_provider, sandbox=Sandbox())

class TestRegisterTransformValidation:
    def test_rejects_empty_expression(self, service):
        with pytest.raises(ValueError, match="'expression' must not be empty"):
            service.register_transform(name="blank", expression="   ")

    def test_rejects_expression_not_returning_expr(self, service):
        with pytest.raises(TypeError, match="must evaluate to a polars Expr"):
            service.register_transform(name="not_expr", expression="1 + 1")

    @pytest.mark.parametrize("name", ["", "1double", "double-it", "double it"])
    def test_rejects_invalid_identifier_name(self, service, name):
        with pytest.raises(ValueError, match="non-empty identifier"):
            service.register_transform(name=name, expression="value * 2")

    def test_rejects_name_already_registered(self, service):
        service.register_transform(name="dup", expression="value * 2")

        with pytest.raises(ValueError, match="already registered"):
            service.register_transform(name="dup", expression="value * 2")

class TestPersistAndRegisterRollback:
    def test_deletes_persisted_definition_when_registration_fails(self, repository, tmp_path):
        class _ExplodingRegistry:
            def keys(self):
                return []

            def register_dynamic(self, key, operator_cls):
                raise RuntimeError("boom")

        class _ExplodingRegistryProvider:
            def get(self, bucket=None):
                return _ExplodingRegistry()

        service = LibraryService(repository=repository, registry_provider=_ExplodingRegistryProvider(), sandbox=Sandbox())

        with pytest.raises(RuntimeError, match="boom"):
            service.register_transform(name="doomed", expression="value * 2")

        assert not (tmp_path / ".node_library" / "doomed.json").exists()

class TestLoadPersistedSkipsAlreadyRegistered:
    def test_skips_names_already_in_registry(self, repository, registry_provider, registry):
        service = LibraryService(repository=repository, registry_provider=registry_provider, sandbox=Sandbox())
        service.register_transform(name="double", expression="value * 2")

        calls = []
        original_register_dynamic = registry.register_dynamic

        def _tracking_register_dynamic(key, operator_cls):
            calls.append(key)
            return original_register_dynamic(key, operator_cls)

        registry.register_dynamic = _tracking_register_dynamic
        service.load_persisted()

        assert calls == []
        assert "double" in registry.keys()

class TestDescribeOperator:
    def test_describes_builtin_operator(self, service, registry):
        operator_cls = registry.get("select")

        description = service.describe_operator(operator_cls)

        assert description["type"] == "select"
        assert description["required"] == {"columns": "list[str]"}
        assert description["ports_out"] == ["out"]
        assert description["fan_in"] is False
        assert description["in_ports"] is None

    def test_describes_fan_in_operator_with_in_ports(self, service, registry):
        operator_cls = registry.get("join")

        description = service.describe_operator(operator_cls)

        assert description["fan_in"] is True
        assert description["in_ports"] == ["left", "right"]

    def test_describes_custom_transform_operator(self, service):
        definition = service.register_transform(name="double", expression="value * 2")
        node_cls = _build_operator_class(definition)

        description = service.describe_operator(node_cls)

        assert description["type"] == "double"
        assert description["required"] == {"columns": "list[str]"}

class TestDescribeNodes:
    def test_includes_builtin_and_custom(self, service):
        service.register_transform(name="double", expression="value * 2")

        data = service.describe_nodes()

        builtin_types = {d["type"] for d in data["builtin"]}
        custom_types = {d["type"] for d in data["custom"]}
        assert "select" in builtin_types
        assert "double" in custom_types

    def test_excludes_custom_from_builtin(self, service):
        service.register_transform(name="double", expression="value * 2")

        data = service.describe_nodes()

        builtin_types = {d["type"] for d in data["builtin"]}
        assert "double" not in builtin_types