import sys
from pathlib import Path

import pytest

from tabular_manner.engine.infrastructure.resource_storage.local_resource_storage_repository import (
    LocalResourceStorageRepository,
)

@pytest.fixture
def repository(tmp_path):
    return LocalResourceStorageRepository(root=str(tmp_path / ".resource_storage"))

class TestResolveWritePath:
    def test_resolve_write_path_creates_bucket_dir(self, repository, tmp_path):
        path = repository.resolve_write_path(key="raw.parquet")

        assert Path(path).parent.name == "default"
        assert Path(path).parent.exists()

    def test_resolve_write_path_uses_given_bucket(self, repository):
        path = repository.resolve_write_path(key="raw.parquet", bucket="team_a")

        assert Path(path).parent.name == "team_a"

class TestGetObject:
    def test_get_object_raises_when_missing(self, repository):
        with pytest.raises(KeyError, match="No resource found"):
            repository.get_object(key="ghost.parquet")

    def test_get_object_returns_path_when_present(self, repository):
        path = Path(repository.resolve_write_path(key="raw.parquet"))
        path.write_bytes(b"data")

        result = repository.get_object(key="raw.parquet")

        assert result == str(path)

class TestList:
    def test_list_empty_bucket_returns_empty(self, repository):
        assert repository.list() == []

    def test_list_returns_files_in_bucket(self, repository):
        path = Path(repository.resolve_write_path(key="raw.parquet"))
        path.write_bytes(b"data")

        assert repository.list() == ["raw.parquet"]

class TestDelete:
    def test_delete_removes_file(self, repository):
        path = Path(repository.resolve_write_path(key="raw.parquet"))
        path.write_bytes(b"data")

        repository.delete(key="raw.parquet")

        assert not path.exists()

    def test_delete_missing_raises(self, repository):
        with pytest.raises(KeyError, match="No resource found"):
            repository.delete(key="ghost.parquet")

class TestPathTraversalGuard:
    @pytest.mark.parametrize(
        "key",
        [
            "../../../etc/passwd",
            "../secret.txt",
            "/etc/passwd",
            "a/../../b",
        ],
    )
    def test_resolve_write_path_rejects_traversal_key(self, repository, key):
        with pytest.raises(ValueError, match="Invalid key"):
            repository.resolve_write_path(key=key)

    @pytest.mark.parametrize(
        "key",
        [
            "../../../etc/passwd",
            "/etc/passwd",
        ],
    )
    def test_get_object_rejects_traversal_key(self, repository, key):
        with pytest.raises(ValueError, match="Invalid key"):
            repository.get_object(key=key)

    @pytest.mark.parametrize(
        "key",
        [
            "../../../etc/passwd",
            "/etc/passwd",
        ],
    )
    def test_delete_rejects_traversal_key(self, repository, key):
        with pytest.raises(ValueError, match="Invalid key"):
            repository.delete(key=key)

    @pytest.mark.parametrize(
        "bucket",
        [
            "../../../etc",
            "/etc",
            "a/../..",
        ],
    )
    def test_rejects_traversal_bucket(self, repository, bucket):
        with pytest.raises(ValueError, match="Invalid bucket name"):
            repository.resolve_write_path(key="raw.parquet", bucket=bucket)

    def test_empty_key_rejected(self, repository):
        with pytest.raises(ValueError, match="'key' must not be empty"):
            repository.resolve_write_path(key="")
