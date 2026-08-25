from ...application.ports.resource_storage_repository import ResourceStorageRepository
from ..s3.config import build_boto3_client, build_storage_options

class S3ResourceStorageRepository(ResourceStorageRepository):
    def __init__(
        self,
        bucket_name: str,
        root_prefix: str = "",
        namespace: str = "",
        region: str = "us-east-1",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        allow_http: bool = False,
        path_style: bool = True,
    ):
        self._bucket_name = bucket_name
        self._root_prefix = root_prefix.strip("/")
        self._namespace = namespace.strip("/")
        self._storage_options = build_storage_options(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            allow_http=allow_http,
            path_style=path_style,
        )
        self._client = build_boto3_client(
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            path_style=path_style,
        )

    @property
    def storage_options(self) -> dict[str, str] | None:
        return self._storage_options

    def _resolve_key(self, key: str, bucket: str | None = None) -> str:
        if not key or not key.strip():
            raise ValueError("'key' must not be empty")
        segments = [segment for segment in (self._root_prefix, bucket, self._namespace, key) if segment]
        return "/".join(segments)

    def _resolve_prefix(self, bucket: str | None = None) -> str:
        segments = [segment for segment in (self._root_prefix, bucket, self._namespace) if segment]
        prefix = "/".join(segments)
        return f"{prefix}/" if prefix else ""

    def resolve_write_path(self, key: str, bucket: str | None = None) -> str:
        object_key = self._resolve_key(key, bucket)
        return f"s3://{self._bucket_name}/{object_key}"

    def get_object(self, key: str, bucket: str | None = None) -> str:
        object_key = self._resolve_key(key, bucket)
        try:
            self._client.head_object(Bucket=self._bucket_name, Key=object_key)
        except self._client.exceptions.ClientError as exc:
            raise KeyError(f"No resource found under key '{key}'") from exc
        return f"s3://{self._bucket_name}/{object_key}"

    def list(self, bucket: str | None = None) -> list[str]:
        prefix = self._resolve_prefix(bucket)
        paginator = self._client.get_paginator("list_objects_v2")
        names = []
        for page in paginator.paginate(Bucket=self._bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                names.append(obj["Key"][len(prefix):])
        return sorted(names)

    def delete(self, key: str, bucket: str | None = None) -> None:
        object_key = self._resolve_key(key, bucket)
        try:
            self._client.head_object(Bucket=self._bucket_name, Key=object_key)
        except self._client.exceptions.ClientError as exc:
            raise KeyError(f"No resource found under key '{key}'") from exc
        self._client.delete_object(Bucket=self._bucket_name, Key=object_key)
