import sys
from pathlib import Path

import polars as pl
import pytest


from tabular_manner.engine.application.storage.resource_storage import ResourceStorage
from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def storage(tmp_path):
    repository = LocalResourceStorageRepository(root=str(tmp_path / ".resource_storage"))
    return ResourceStorage(repository=repository)

class TestSaveAndLoad:
    def test_save_then_load_roundtrips_data(self, storage):
        storage.save("raw", pl.DataFrame({"a": [1, 2]}).lazy())

        loaded = storage.load("raw").collect()

        assert loaded["a"].to_list() == [1, 2]

    def test_save_respects_explicit_bucket(self, storage):
        storage.save("raw", pl.DataFrame({"a": [1]}).lazy(), bucket="team_a")

        assert storage.list(bucket="team_a") == ["raw"]
        assert storage.list() == []

class TestList:
    def test_list_returns_keys_without_extension(self, storage):
        storage.save("raw", pl.DataFrame({"a": [1]}).lazy())
        storage.save("cleaned", pl.DataFrame({"a": [1]}).lazy())

        assert storage.list() == ["cleaned", "raw"]

    def test_list_empty_bucket_returns_empty_list(self, storage):
        assert storage.list() == []

class TestDelete:
    def test_delete_removes_resource(self, storage):
        storage.save("raw", pl.DataFrame({"a": [1]}).lazy())

        storage.delete("raw")

        assert storage.list() == []

    def test_delete_missing_resource_raises(self, storage):
        with pytest.raises(KeyError):
            storage.delete("does_not_exist")

    def test_delete_respects_bucket(self, storage):
        storage.save("raw", pl.DataFrame({"a": [1]}).lazy(), bucket="team_a")

        storage.delete("raw", bucket="team_a")

        assert storage.list(bucket="team_a") == []

    def test_delete_does_not_affect_other_bucket(self, storage):
        storage.save("raw", pl.DataFrame({"a": [1]}).lazy(), bucket="team_a")
        storage.save("raw", pl.DataFrame({"a": [1]}).lazy(), bucket="team_b")

        storage.delete("raw", bucket="team_a")

        assert storage.list(bucket="team_b") == ["raw"]
