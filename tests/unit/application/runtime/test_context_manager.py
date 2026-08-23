import sys
from pathlib import Path

import pytest

from tabular_manner.engine.application.runtime.context_manager import ContextManager

class TestRegisterAndGet:
    def test_get_returns_registered_resource(self):
        manager = ContextManager()
        manager.register("storage", "a_resource")

        assert manager.get("storage") == "a_resource"

    def test_register_returns_self_for_chaining(self):
        manager = ContextManager()

        result = manager.register("a", 1).register("b", 2)

        assert result is manager
        assert manager.get("a") == 1
        assert manager.get("b") == 2

    def test_get_raises_for_unknown_resource(self):
        manager = ContextManager()

        with pytest.raises(ValueError, match="Resource not found: storage"):
            manager.get("storage")

class TestInject:
    def test_binds_resources_into_node_operators(self):
        manager = ContextManager()
        manager.register("resource_storage", "a_resource")

        class _FakeOperator:
            def __init__(self):
                self.bound = None

            def bind(self, resources):
                self.bound = resources

        class _FakeNode:
            def __init__(self):
                self.operator = _FakeOperator()

        node = _FakeNode()
        manager.inject({"1": node})

        assert node.operator.bound == {"resource_storage": "a_resource"}
