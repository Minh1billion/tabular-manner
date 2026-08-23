import sys
from pathlib import Path

import polars as pl
import pytest


from tabular_manner.engine.application.nodes.custom_node_service import LibraryService, _build_operator_class
from tabular_manner.engine.application.nodes.registry import NodeRegistry
from tabular_manner.engine.application.runtime.sandbox import Sandbox
from tabular_manner.engine.application.storage.resource_storage import ResourceStorage
from tabular_manner.engine.domain.models.custom_node import CustomNodeDefinition
from tabular_manner.engine.domain.models.plan import Plan
from tabular_manner.engine.infrastructure.node_library.local_node_library_repository import LocalNodeLibraryRepository
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def repository(tmp_path):
    return LocalNodeLibraryRepository(root=str(tmp_path / ".node_library"))

@pytest.fixture
def resource_storage(tmp_path):
    return ResourceStorage(
        repository=LocalResourceStorageRepository(root=str(tmp_path / ".resource_storage")),
    )

@pytest.fixture
def registry():
    return NodeRegistry()

@pytest.fixture
def service(repository, registry):
    return LibraryService(repository=repository, registry=registry, sandbox=Sandbox())

class TestBuildOperatorClassUnknownKind:
    def test_raises_for_unknown_kind(self):
        definition = CustomNodeDefinition(
            name="bogus", kind="not_a_kind", description="", created_at="2024-01-01T00:00:00+00:00",
        )

        with pytest.raises(ValueError, match="Unknown custom node kind"):
            _build_operator_class(definition)

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

class TestRegisterActionValidation:
    def test_rejects_blank_handle_param(self, service):
        with pytest.raises(ValueError, match="must not be empty when provided"):
            service.register_action(
                name="peek", service="resource_storage", method="save", handle_param="   ",
            )

    def test_rejects_name_already_registered(self, service):
        service.register_action(name="dup", service="resource_storage", method="save")

        with pytest.raises(ValueError, match="already registered"):
            service.register_action(name="dup", service="resource_storage", method="save")

class TestPersistAndRegisterRollback:
    def test_deletes_persisted_definition_when_registration_fails(self, repository, tmp_path):
        class _ExplodingRegistry:
            def keys(self):
                return []

            def register_dynamic(self, key, operator_cls):
                raise RuntimeError("boom")

        service = LibraryService(repository=repository, registry=_ExplodingRegistry(), sandbox=Sandbox())

        with pytest.raises(RuntimeError, match="boom"):
            service.register_transform(name="doomed", expression="value * 2")

        assert not (tmp_path / ".node_library" / "doomed.json").exists()

class TestLoadPersistedSkipsAlreadyRegistered:
    def test_skips_names_already_in_registry(self, repository, registry):
        service = LibraryService(repository=repository, registry=registry, sandbox=Sandbox())
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

class TestCustomActionOperator:
    def test_handle_param_collision_raises_on_instantiation(self, service):
        definition = service.register_action(
            name="custom_load", service="resource_storage", method="load", handle_param="key",
        )
        node_cls = _build_operator_class(definition)

        with pytest.raises(ValueError, match="collides with 'handle_param'"):
            node_cls(name="custom_load", key="raw")

    def test_forward_commits_when_action_returns_lazyframe(self, service, resource_storage):
        resource_storage.save("raw", pl.DataFrame({"a": [1, 2]}).lazy())

        definition = service.register_action(name="custom_load", service="resource_storage", method="load")
        node_cls = _build_operator_class(definition)
        node = node_cls(name="custom_load", key="raw")
        node.bind({"resource_storage": resource_storage})

        plan = Plan(handle=pl.LazyFrame())
        result_plan, port = node.forward(plan)

        assert port == "out"
        assert result_plan.history[-1] == "custom_load"
        assert result_plan.handle.collect()["a"].to_list() == [1, 2]

    def test_forward_keeps_plan_when_action_returns_none(self, service, resource_storage):
        definition = service.register_action(
            name="custom_save", service="resource_storage", method="save", handle_param="lf",
        )
        node_cls = _build_operator_class(definition)
        node = node_cls(name="custom_save", key="processed")
        node.bind({"resource_storage": resource_storage})

        plan = Plan(handle=pl.LazyFrame({"a": [1]}))
        result_plan, port = node.forward(plan)

        assert result_plan is plan
        assert port == "out"
        assert resource_storage.list() == ["processed"]
