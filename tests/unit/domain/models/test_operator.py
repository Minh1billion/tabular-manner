import pytest

from tabular_manner.engine.domain.models.operator import Operator, SchemaStrategy
from tabular_manner.engine.domain.models.plan import Plan

class _Simple(Operator):
    required = {"columns": (list, str)}
    optional = {"limit": (int, 10)}

class _NoParams(Operator):
    pass

class _MultiPort(Operator):
    ports = ("true", "false")

class TestOperatorValidation:
    def test_required_field_missing_raises(self):
        with pytest.raises(ValueError, match="'columns' is required"):
            _Simple()

    def test_required_field_wrong_type_raises(self):
        with pytest.raises(TypeError, match="'columns' must be of type list\\[str\\]"):
            _Simple(columns="not_a_list")

    def test_required_field_valid_sets_attribute(self):
        op = _Simple(columns=["a", "b"])
        assert op.columns == ["a", "b"]

    def test_optional_field_uses_default_when_missing(self):
        op = _Simple(columns=["a"])
        assert op.limit == 10

    def test_optional_field_overridden(self):
        op = _Simple(columns=["a"], limit=5)
        assert op.limit == 5

    def test_optional_field_wrong_type_raises(self):
        with pytest.raises(TypeError, match="'limit' must be of type int"):
            _Simple(columns=["a"], limit="five")

    def test_optional_field_allows_none(self):
        op = _Simple(columns=["a"], limit=None)
        assert op.limit is None

    def test_list_type_rejects_non_list(self):
        with pytest.raises(TypeError):
            _Simple(columns={"a": 1})

    def test_list_type_rejects_mixed_element_types(self):
        with pytest.raises(TypeError):
            _Simple(columns=["a", 1])

class TestOperatorNaming:
    def test_name_defaults_to_type(self):
        op = _NoParams()
        assert op.name == "_noparams"
        assert op.type == "_noparams"

    def test_name_can_be_overridden(self):
        op = _NoParams(name="custom")
        assert op.name == "custom"

class TestOperatorPorts:
    def test_default_port_is_out(self):
        op = _NoParams()
        assert op.valid_ports() == ("out",)

    def test_custom_ports_override_default(self):
        op = _MultiPort()
        assert op.valid_ports() == ("true", "false")

class TestOperatorBind:
    def test_bind_sets_attributes_from_context_keys(self):
        class _WithContext(Operator):
            context = ("resource_storage",)

        op = _WithContext()
        sentinel = object()
        op.bind({"resource_storage": sentinel, "unused": object()})

        assert op.resource_storage is sentinel

    def test_bind_ignores_missing_resources(self):
        class _WithContext(Operator):
            context = ("resource_storage",)

        op = _WithContext()
        op.bind({})

        assert not hasattr(op, "resource_storage")

class TestOperatorForwardNotImplemented:
    def test_forward_raises_not_implemented(self):
        op = _NoParams()
        with pytest.raises(NotImplementedError):
            op.forward(Plan(handle=None))

    def test_forward_many_raises_not_implemented(self):
        op = _NoParams()
        with pytest.raises(NotImplementedError):
            op.forward_many([])

class TestOperatorSchemaContract:
    def test_declared_strategy_without_override_raises_at_class_definition(self):
        with pytest.raises(TypeError, match="declared_schema"):
            class _Bad(Operator):
                schema_strategy = SchemaStrategy.DECLARED

    def test_declared_strategy_with_override_defines_successfully(self):
        class _Good(Operator):
            schema_strategy = SchemaStrategy.DECLARED

            def declared_schema(self, input_schema):
                return input_schema

        assert _Good.schema_strategy is SchemaStrategy.DECLARED

    def test_structural_strategy_is_default(self):
        assert _NoParams.schema_strategy is SchemaStrategy.STRUCTURAL

    def test_declared_schema_raises_not_implemented_by_default(self):
        op = _NoParams()
        with pytest.raises(NotImplementedError):
            op.declared_schema(None)

    def test_declared_schema_many_raises_not_implemented_by_default(self):
        op = _NoParams()
        with pytest.raises(NotImplementedError):
            op.declared_schema_many([])