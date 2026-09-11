import pytest

from tabular_manner.engine.application.nodes.registry import NodeRegistry
from tabular_manner.engine.domain.models.operator import Operator, SchemaStrategy

@pytest.mark.parametrize("key", sorted(NodeRegistry._builtin_registry.keys()))
def test_declared_nodes_override_declared_schema(key):
    cls = NodeRegistry._builtin_registry[key]

    if cls.schema_strategy is SchemaStrategy.DECLARED:
        assert cls.declared_schema is not Operator.declared_schema
        assert cls.declared_schema is not Operator.declared_schema_many