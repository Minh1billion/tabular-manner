import sys
from pathlib import Path

import pytest


from tabular_manner.engine.domain.models.custom_node import CustomNodeDefinition
from tabular_manner.engine.infrastructure.node_library.local_node_library_repository import (
    LocalNodeLibraryRepository,
)

@pytest.fixture
def repository(tmp_path):
    return LocalNodeLibraryRepository(root=str(tmp_path / ".node_library"))

def _definition(name="double") -> CustomNodeDefinition:
    return CustomNodeDefinition(
        name=name,
        kind="transform",
        description="doubles a column",
        created_at="2026-01-01T00:00:00+00:00",
        expression="value * 2",
    )

class TestSaveAndGet:
    def test_save_then_get_roundtrips(self, repository):
        repository.save(_definition())

        loaded = repository.get("double")

        assert loaded == _definition()

    def test_get_missing_raises(self, repository):
        with pytest.raises(KeyError, match="No custom transform found"):
            repository.get("does_not_exist")

class TestDelete:
    def test_delete_removes_definition(self, repository):
        repository.save(_definition())

        repository.delete("double")

        with pytest.raises(KeyError):
            repository.get("double")

    def test_delete_missing_raises(self, repository):
        with pytest.raises(KeyError, match="No custom transform found"):
            repository.delete("does_not_exist")

class TestList:
    def test_list_empty_returns_empty(self, repository):
        assert repository.list() == []

    def test_list_returns_all_saved_definitions_sorted_by_name(self, repository):
        repository.save(_definition("double"))
        repository.save(_definition("triple"))

        names = [d.name for d in repository.list()]

        assert names == ["double", "triple"]
