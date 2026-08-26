import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .application.io.reader_factory import ReaderFactory
from .application.io.writer_factory import WriterFactory
from .application.storage.object_storage import ObjectStorage
from .bootstrap import Engine, build_engine

@dataclass(frozen=True)
class EngineSettings:
    backend: str = "local"
    storage_root: str = ".tm"
    s3_bucket_name: str | None = None
    s3_root_prefix: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_allow_http: bool = False
    s3_path_style: bool = True
    max_cached_graphs: int = 128
    bucket_idle_ttl: timedelta | None = None
    warm_buckets: tuple[str, ...] = ()

class EngineLifecycle:
    def __init__(self, settings: EngineSettings):
        self._settings = settings
        self._engine: Engine | None = None
        self._lock = threading.Lock()
        self._bucket_last_used: dict[str, datetime] = {}

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("EngineLifecycle has not been started")
        return self._engine

    def start(self) -> Engine:
        with self._lock:
            if self._engine is not None:
                return self._engine

            object_storage = ObjectStorage(
                backend=self._settings.backend,
                root=self._settings.storage_root,
                s3_bucket_name=self._settings.s3_bucket_name,
                s3_root_prefix=self._settings.s3_root_prefix,
                s3_region=self._settings.s3_region,
                s3_endpoint_url=self._settings.s3_endpoint_url,
                s3_access_key_id=self._settings.s3_access_key_id,
                s3_secret_access_key=self._settings.s3_secret_access_key,
                s3_allow_http=self._settings.s3_allow_http,
                s3_path_style=self._settings.s3_path_style,
            )

            engine = build_engine(
                object_storage=object_storage,
                reader_factory=ReaderFactory(),
                writer_factory=WriterFactory(),
                storage_root=self._settings.storage_root,
                max_cached_graphs=self._settings.max_cached_graphs,
            )

            now = datetime.now(timezone.utc)
            for bucket in self._settings.warm_buckets:
                engine.node_library.load_persisted(bucket)
                self._bucket_last_used[bucket] = now

            self._engine = engine
            return engine

    def stop(self) -> None:
        with self._lock:
            if self._engine is None:
                return
            self._engine.object_storage.close()
            self._engine = None
            self._bucket_last_used.clear()

    def healthcheck(self) -> bool:
        with self._lock:
            engine = self._engine
        if engine is None:
            return False
        try:
            engine.node_library.load_persisted()
            return True
        except Exception:
            return False

    def touch_bucket(self, bucket: str) -> None:
        with self._lock:
            self._bucket_last_used[bucket] = datetime.now(timezone.utc)

    def evict_idle_buckets(self) -> list[str]:
        ttl = self._settings.bucket_idle_ttl
        with self._lock:
            if ttl is None or self._engine is None:
                return []
            cutoff = datetime.now(timezone.utc) - ttl
            expired = [bucket for bucket, last_used in self._bucket_last_used.items() if last_used < cutoff]
            for bucket in expired:
                self._engine.registry_provider.evict(bucket)
                del self._bucket_last_used[bucket]
            return expired