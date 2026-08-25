from unittest.mock import MagicMock

import pytest

from tabular_manner.engine.api.node_library import NodeLibrary
from tabular_manner.engine.domain.models.custom_node import CustomNodeDefinition

def _definition(name: str = "double") -> CustomNodeDefinition:
    return CustomNodeDefinition(
        name=name,
        description="",
        created_at="2024-01-01T00:00:00+00:00",
        expression="value * 2",
    )

@pytest.fixture
def service():
    return MagicMock()

@pytest.fixture
def node_library(service):
    return NodeLibrary(service=service)

class TestRegisterTransform:
    def test_yields_completed_event_on_success(self, node_library, service):
        service.register_transform.return_value = _definition()

        events = list(node_library.register_transform(name="double", expression="value * 2"))

        assert [e["event"] for e in events] == ["validating", "completed"]
        assert events[-1]["data"]["name"] == "double"

    def test_yields_failed_event_on_error(self, node_library, service):
        service.register_transform.side_effect = ValueError("bad expression")

        events = list(node_library.register_transform(name="double", expression="???"))

        assert [e["event"] for e in events] == ["validating", "failed"]
        assert events[-1]["error"] == "bad expression"

class TestUnregisterNode:
    def test_yields_failed_event_on_error(self, node_library, service):
        service.unregister_transform.side_effect = KeyError("unknown")

        events = list(node_library.unregister_node("ghost"))

        assert [e["event"] for e in events] == ["unregistering", "failed"]

class TestGetNode:
    def test_yields_completed_event_on_success(self, node_library, service):
        service.get_transform.return_value = _definition()

        events = list(node_library.get_node("double"))

        assert [e["event"] for e in events] == ["loading", "completed"]

    def test_yields_failed_event_when_not_found(self, node_library, service):
        service.get_transform.side_effect = KeyError("No custom transform found under name 'ghost'")

        events = list(node_library.get_node("ghost"))

        assert [e["event"] for e in events] == ["loading", "failed"]
        assert "ghost" in events[-1]["error"]

class TestListNodes:
    def test_yields_completed_event_on_success(self, node_library, service):
        service.list_transforms.return_value = [_definition()]
        service.builtin_keys.return_value = ["select"]

        events = list(node_library.list_nodes())

        assert [e["event"] for e in events] == ["listing", "completed"]
        assert events[-1]["data"]["builtin"] == ["select"]
        assert events[-1]["data"]["custom"][0]["name"] == "double"

    def test_yields_failed_event_when_service_raises(self, node_library, service):
        service.list_transforms.side_effect = RuntimeError("storage unavailable")

        events = list(node_library.list_nodes())

        assert [e["event"] for e in events] == ["listing", "failed"]
        assert events[-1]["error"] == "storage unavailable"