from typing import Any, Iterator

import polars as pl
import pyarrow.parquet as pq

from ...application.ports.resource_storage_repository import ResourceStorageRepository
from ..s3.config import build_boto3_client, build_storage_options

class _MultipartBuffer:
    def __init__(self):
        self._pending = bytearray()
        self._pos = 0
        self.closed = False

    def write(self, data: bytes) -> int:
        self._pending.extend(data)
        self._pos += len(data)
        return len(data)

    def tell(self) -> int:
        return self._pos

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def pending_size(self) -> int:
        return len(self._pending)

    def drain(self) -> bytes:
        data = bytes(self._pending)
        self._pending.clear()
        return data

class S3ResourceStorageRepository(ResourceStorageRepository):
    supports_streaming_write = True
    MIN_PART_SIZE = 5 * 1024 * 1024

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

    def close(self) -> None:
        if hasattr(self._client, "close"):
            self._client.close()

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

    def save_streaming(
        self,
        key: str,
        lf: pl.LazyFrame,
        total: int | None,
        chunk_size: int,
        bucket: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        object_key = self._resolve_key(key, bucket)
        buffer = _MultipartBuffer()
        writer: pq.ParquetWriter | None = None
        upload_id: str | None = None
        parts: list[dict[str, Any]] = []
        part_number = 1
        processed = 0
        wrote_any_batch = False

        def flush_part(final: bool = False) -> None:
            nonlocal part_number
            if buffer.pending_size() == 0:
                return
            if not final and buffer.pending_size() < self.MIN_PART_SIZE:
                return
            data = buffer.drain()
            response = self._client.upload_part(
                Bucket=self._bucket_name,
                Key=object_key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=data,
            )
            parts.append({"ETag": response["ETag"], "PartNumber": part_number})
            part_number += 1

        try:
            for batch in lf.collect_batches(chunk_size=chunk_size):
                if not wrote_any_batch:
                    wrote_any_batch = True
                    upload = self._client.create_multipart_upload(Bucket=self._bucket_name, Key=object_key)
                    upload_id = upload["UploadId"]
                table = batch.to_arrow()
                if writer is None:
                    writer = pq.ParquetWriter(buffer, table.schema)
                writer.write_table(table)
                processed += batch.height
                flush_part()
                yield {"processed": processed, "total": total}
        except BaseException:
            if writer is not None:
                writer.close()
            if upload_id is not None:
                self._client.abort_multipart_upload(
                    Bucket=self._bucket_name, Key=object_key, UploadId=upload_id
                )
            raise
        else:
            if not wrote_any_batch:
                lf.sink_parquet(
                    self.resolve_write_path(key, bucket),
                    storage_options=self.storage_options,
                )
                return
            writer.close()
            flush_part(final=True)
            self._client.complete_multipart_upload(
                Bucket=self._bucket_name,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

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