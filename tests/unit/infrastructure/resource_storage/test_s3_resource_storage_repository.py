import io

import polars as pl
import pyarrow.parquet as pq
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

class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.calls: list[str] = []
        self._uploads: dict[str, dict[int, bytes]] = {}
        self._next_upload_id = 1

    def create_multipart_upload(self, Bucket, Key):
        self.calls.append("create_multipart_upload")
        upload_id = f"upload-{self._next_upload_id}"
        self._next_upload_id += 1
        self._uploads[upload_id] = {}
        return {"UploadId": upload_id}

    def upload_part(self, Bucket, Key, UploadId, PartNumber, Body):
        self.calls.append("upload_part")
        self._uploads[UploadId][PartNumber] = Body
        return {"ETag": f"etag-{UploadId}-{PartNumber}"}

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        self.calls.append("complete_multipart_upload")
        parts = sorted(MultipartUpload["Parts"], key=lambda p: p["PartNumber"])
        data = b"".join(self._uploads[UploadId][p["PartNumber"]] for p in parts)
        self.objects[Key] = data
        del self._uploads[UploadId]

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.calls.append("abort_multipart_upload")
        self._uploads.pop(UploadId, None)

@pytest.fixture
def fake_client(repository):
    fake = _FakeS3Client()
    repository._client = fake
    return fake

class TestSaveStreaming:
    def test_multiple_parts_uploaded_when_total_exceeds_threshold(self, repository, fake_client):
        repository.MIN_PART_SIZE = 200

        lf = pl.LazyFrame({"a": range(5_000)})
        events = list(
            repository.save_streaming(key="raw.parquet", lf=lf, total=5_000, chunk_size=500)
        )

        upload_part_calls = fake_client.calls.count("upload_part")
        assert upload_part_calls > 1
        assert fake_client.calls[0] == "create_multipart_upload"
        assert fake_client.calls[-1] == "complete_multipart_upload"
        assert events[-1] == {"processed": 5_000, "total": 5_000}

    def test_round_trip_reads_back_correct_data(self, repository, fake_client):
        repository.MIN_PART_SIZE = 200

        lf = pl.LazyFrame({"a": range(5_000)})
        list(repository.save_streaming(key="raw.parquet", lf=lf, total=5_000, chunk_size=500))

        data = fake_client.objects["data/raw.parquet"]
        table = pq.read_table(io.BytesIO(data))
        assert table.num_rows == 5_000
        assert table.column("a").to_pylist() == list(range(5_000))

    def test_abort_called_when_write_is_cancelled_mid_stream(self, repository, fake_client, monkeypatch):
        repository.MIN_PART_SIZE = 200

        real_collect_batches = pl.LazyFrame.collect_batches

        def _boom(self, *args, **kwargs):
            for i, batch in enumerate(real_collect_batches(self, *args, **kwargs)):
                if i == 2:
                    raise RuntimeError("boom")
                yield batch

        monkeypatch.setattr(pl.LazyFrame, "collect_batches", _boom)

        lf = pl.LazyFrame({"a": range(5_000)})
        with pytest.raises(RuntimeError, match="boom"):
            list(repository.save_streaming(key="raw.parquet", lf=lf, total=5_000, chunk_size=500))

        assert "abort_multipart_upload" in fake_client.calls
        assert "complete_multipart_upload" not in fake_client.calls
        assert "data/raw.parquet" not in fake_client.objects

    def test_empty_batches_fall_back_to_plain_save(self, repository, fake_client, monkeypatch):
        called = {}

        def fake_sink_parquet(self, path, storage_options=None, **kwargs):
            called["path"] = path

        monkeypatch.setattr(pl.LazyFrame, "sink_parquet", fake_sink_parquet)

        lf = pl.LazyFrame({"a": pl.Series("a", [], dtype=pl.Int64)})
        events = list(repository.save_streaming(key="raw.parquet", lf=lf, total=0, chunk_size=500))

        assert events == []
        assert fake_client.calls == []
        assert called["path"] == "s3://my-bucket/data/raw.parquet"

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
