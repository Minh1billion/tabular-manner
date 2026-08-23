import io
import json
import sys
from pathlib import Path

import pytest
from botocore.stub import Stubber


from tabular_manner.engine.domain.models.custom_node import CustomNodeDefinition
from tabular_manner.engine.infrastructure.node_library.s3_node_library_repository import (
    S3NodeLibraryRepository,
)

@pytest.fixture
def repository():
    return S3NodeLibraryRepository(bucket_name="my-bucket", root_prefix="node_library")

@pytest.fixture
def stubber(repository):
    stubber = Stubber(repository._client)
    stubber.activate()
    yield stubber
    stubber.deactivate()

def _definition(name: str = "double") -> CustomNodeDefinition:
    return CustomNodeDefinition(
        name=name,
        kind="transform",
        description="Doubles a numeric column",
        created_at="2024-01-01T00:00:00+00:00",
        expression="value * 2",
    )

def _body_stream(payload: dict) -> "io.BytesIO":
    return io.BytesIO(json.dumps(payload).encode("utf-8"))

class TestSave:
    def test_puts_json_body_under_prefixed_key(self, repository, stubber):
        definition = _definition()

        stubber.add_response(
            "put_object",
            {},
            {
                "Bucket": "my-bucket",
                "Key": "node_library/double.json",
                "Body": json.dumps(
                    {
                        "name": "double",
                        "kind": "transform",
                        "description": "Doubles a numeric column",
                        "created_at": "2024-01-01T00:00:00+00:00",
                        "expression": "value * 2",
                        "service": None,
                        "method": None,
                        "handle_param": None,
                    },
                    indent=2,
                ).encode("utf-8"),
                "ContentType": "application/json",
            },
        )

        repository.save(definition)

        stubber.assert_no_pending_responses()

class TestGet:
    def test_returns_definition_when_present(self, repository, stubber):
        payload = {
            "name": "double",
            "kind": "transform",
            "description": "Doubles a numeric column",
            "created_at": "2024-01-01T00:00:00+00:00",
            "expression": "value * 2",
            "service": None,
            "method": None,
            "handle_param": None,
        }
        stubber.add_response(
            "get_object",
            {"Body": _body_stream(payload)},
            {"Bucket": "my-bucket", "Key": "node_library/double.json"},
        )

        result = repository.get("double")

        assert result == _definition()

    def test_raises_key_error_when_missing(self, repository, stubber):
        stubber.add_client_error(
            "get_object",
            service_error_code="NoSuchKey",
            service_message="Not Found",
            http_status_code=404,
        )

        with pytest.raises(KeyError, match="No custom transform found under name 'double'"):
            repository.get("double")

class TestDelete:
    def test_deletes_existing_definition(self, repository, stubber):
        stubber.add_response(
            "head_object",
            {},
            {"Bucket": "my-bucket", "Key": "node_library/double.json"},
        )
        stubber.add_response(
            "delete_object",
            {},
            {"Bucket": "my-bucket", "Key": "node_library/double.json"},
        )

        repository.delete("double")

        stubber.assert_no_pending_responses()

    def test_raises_key_error_when_missing(self, repository, stubber):
        stubber.add_client_error(
            "head_object",
            service_error_code="404",
            service_message="Not Found",
            http_status_code=404,
        )

        with pytest.raises(KeyError, match="No custom transform found under name 'double'"):
            repository.delete("double")

class TestList:
    def test_returns_definitions_sorted_by_name(self, repository, stubber):
        stubber.add_response(
            "list_objects_v2",
            {
                "Contents": [
                    {"Key": "node_library/double.json"},
                    {"Key": "node_library/add_one.json"},
                    {"Key": "node_library/ignored.txt"},
                ],
            },
            {"Bucket": "my-bucket", "Prefix": "node_library/"},
        )
        stubber.add_response(
            "get_object",
            {"Body": _body_stream(
                {
                    "name": "double",
                    "kind": "transform",
                    "description": "",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "expression": "value * 2",
                    "service": None,
                    "method": None,
                    "handle_param": None,
                }
            )},
            {"Bucket": "my-bucket", "Key": "node_library/double.json"},
        )
        stubber.add_response(
            "get_object",
            {"Body": _body_stream(
                {
                    "name": "add_one",
                    "kind": "transform",
                    "description": "",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "expression": "value + 1",
                    "service": None,
                    "method": None,
                    "handle_param": None,
                }
            )},
            {"Bucket": "my-bucket", "Key": "node_library/add_one.json"},
        )

        result = repository.list()

        assert [definition.name for definition in result] == ["add_one", "double"]

    def test_returns_empty_list_when_no_contents(self, repository, stubber):
        stubber.add_response(
            "list_objects_v2",
            {},
            {"Bucket": "my-bucket", "Prefix": "node_library/"},
        )

        assert repository.list() == []
