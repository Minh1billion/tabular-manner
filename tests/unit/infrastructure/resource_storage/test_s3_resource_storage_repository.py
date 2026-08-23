import sys
from pathlib import Path

import pytest
from botocore.stub import Stubber


from tabular_manner.engine.infrastructure.resource_storage.s3_resource_storage_repository import (
    S3ResourceStorageRepository,
)

@pytest.fixture
def repository():
    return S3ResourceStorageRepository(bucket_name="my-bucket", root_prefix="data")

@pytest.fixture
def stubber(repository):
    stubber = Stubber(repository._client)
    stubber.activate()
    yield stubber
    stubber.deactivate()

class TestResolveWritePath:
    def test_returns_s3_uri_with_prefix_and_bucket(self, repository):
        path = repository.resolve_write_path(key="raw.parquet", bucket="team_a")

        assert path == "s3://my-bucket/data/team_a/raw.parquet"

    def test_returns_s3_uri_without_bucket(self, repository):
        path = repository.resolve_write_path(key="raw.parquet")

        assert path == "s3://my-bucket/data/raw.parquet"

    def test_rejects_empty_key(self, repository):
        with pytest.raises(ValueError, match="'key' must not be empty"):
            repository.resolve_write_path(key="")

class TestGetObject:
    def test_returns_uri_when_object_exists(self, repository, stubber):
        stubber.add_response(
            "head_object",
            {},
            {"Bucket": "my-bucket", "Key": "data/raw.parquet"},
        )

        result = repository.get_object(key="raw.parquet")

        assert result == "s3://my-bucket/data/raw.parquet"
        stubber.assert_no_pending_responses()

    def test_raises_key_error_when_missing(self, repository, stubber):
        stubber.add_client_error(
            "head_object",
            service_error_code="404",
            service_message="Not Found",
            http_status_code=404,
        )

        with pytest.raises(KeyError, match="No resource found under key 'raw.parquet'"):
            repository.get_object(key="raw.parquet")

class TestList:
    def test_returns_sorted_relative_keys(self, repository, stubber):
        stubber.add_response(
            "list_objects_v2",
            {
                "Contents": [
                    {"Key": "data/b.parquet"},
                    {"Key": "data/a.parquet"},
                ],
            },
            {"Bucket": "my-bucket", "Prefix": "data/"},
        )

        result = repository.list()

        assert result == ["a.parquet", "b.parquet"]

    def test_returns_empty_list_when_no_contents(self, repository, stubber):
        stubber.add_response(
            "list_objects_v2",
            {},
            {"Bucket": "my-bucket", "Prefix": "data/"},
        )

        assert repository.list() == []

    def test_scopes_by_bucket_prefix(self, repository, stubber):
        stubber.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "data/team_a/raw.parquet"}]},
            {"Bucket": "my-bucket", "Prefix": "data/team_a/"},
        )

        result = repository.list(bucket="team_a")

        assert result == ["raw.parquet"]

class TestDelete:
    def test_deletes_existing_object(self, repository, stubber):
        stubber.add_response(
            "head_object",
            {},
            {"Bucket": "my-bucket", "Key": "data/raw.parquet"},
        )
        stubber.add_response(
            "delete_object",
            {},
            {"Bucket": "my-bucket", "Key": "data/raw.parquet"},
        )

        repository.delete(key="raw.parquet")

        stubber.assert_no_pending_responses()

    def test_raises_key_error_when_missing(self, repository, stubber):
        stubber.add_client_error(
            "head_object",
            service_error_code="404",
            service_message="Not Found",
            http_status_code=404,
        )

        with pytest.raises(KeyError, match="No resource found under key 'raw.parquet'"):
            repository.delete(key="raw.parquet")

class TestStorageOptions:
    def test_exposes_region_by_default(self):
        repository = S3ResourceStorageRepository(bucket_name="my-bucket")

        assert repository.storage_options["aws_region"] == "us-east-1"

    def test_includes_endpoint_and_credentials_when_provided(self):
        repository = S3ResourceStorageRepository(
            bucket_name="my-bucket",
            endpoint_url="http://localhost:9000",
            access_key_id="AKIA",
            secret_access_key="secret",
            allow_http=True,
        )

        assert repository.storage_options["aws_endpoint_url"] == "http://localhost:9000"
        assert repository.storage_options["aws_access_key_id"] == "AKIA"
        assert repository.storage_options["aws_secret_access_key"] == "secret"
        assert repository.storage_options["aws_allow_http"] == "true"
