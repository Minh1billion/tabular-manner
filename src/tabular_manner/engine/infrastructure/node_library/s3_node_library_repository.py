import json
from dataclasses import asdict

from ...application.ports.node_library_repository import NodeLibraryRepository
from ...domain.models.custom_node import CustomNodeDefinition
from ..s3.config import build_boto3_client

class S3NodeLibraryRepository(NodeLibraryRepository):
    def __init__(
        self,
        bucket_name: str,
        root_prefix: str = "",
        namespace: str = "",
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        path_style: bool = True,
    ):
        self._bucket_name = bucket_name
        self._root_prefix = root_prefix.strip("/")
        self._namespace = namespace.strip("/")
        self._client = build_boto3_client(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            path_style=path_style,
        )

    def close(self) -> None:
        if hasattr(self._client, "close"):
            self._client.close()

    def _key(self, name: str, bucket: str | None = None) -> str:
        if not name or not name.strip() or "/" in name or name in (".", ".."):
            raise ValueError(f"Invalid name '{name}'")
        segments = [segment for segment in (self._root_prefix, bucket, self._namespace, f"{name}.json") if segment]
        return "/".join(segments)

    def _prefix(self, bucket: str | None = None) -> str:
        segments = [segment for segment in (self._root_prefix, bucket, self._namespace) if segment]
        prefix = "/".join(segments)
        return f"{prefix}/" if prefix else ""

    def save(self, definition: CustomNodeDefinition, bucket: str | None = None) -> None:
        self._client.put_object(
            Bucket=self._bucket_name,
            Key=self._key(definition.name, bucket),
            Body=json.dumps(asdict(definition), indent=2).encode("utf-8"),
            ContentType="application/json",
        )

    def get(self, name: str, bucket: str | None = None) -> CustomNodeDefinition:
        try:
            response = self._client.get_object(Bucket=self._bucket_name, Key=self._key(name, bucket))
        except self._client.exceptions.NoSuchKey as exc:
            raise KeyError(f"No custom transform found under name '{name}'") from exc
        return CustomNodeDefinition(**json.loads(response["Body"].read()))

    def delete(self, name: str, bucket: str | None = None) -> None:
        key = self._key(name, bucket)
        try:
            self._client.head_object(Bucket=self._bucket_name, Key=key)
        except self._client.exceptions.ClientError as exc:
            raise KeyError(f"No custom transform found under name '{name}'") from exc
        self._client.delete_object(Bucket=self._bucket_name, Key=key)

    def list(self, bucket: str | None = None) -> list[CustomNodeDefinition]:
        prefix = self._prefix(bucket)
        paginator = self._client.get_paginator("list_objects_v2")
        definitions = []
        for page in paginator.paginate(Bucket=self._bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                if not obj["Key"].endswith(".json"):
                    continue
                response = self._client.get_object(Bucket=self._bucket_name, Key=obj["Key"])
                definitions.append(CustomNodeDefinition(**json.loads(response["Body"].read())))
        return sorted(definitions, key=lambda d: d.name)