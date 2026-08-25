from typing import Callable

from ..ports.node_library_repository import NodeLibraryRepository
from ..ports.resource_storage_repository import ResourceStorageRepository

BackendFactory = Callable[["ObjectStorage"], tuple[ResourceStorageRepository, NodeLibraryRepository]]

class ObjectStorage:
    RESOURCE_NAMESPACE = ".resource"
    NODE_LIB_NAMESPACE = ".node_lib"

    _backends: dict[str, BackendFactory] = {}

    @classmethod
    def register_backend(cls, key: str):
        def wrapper(factory: BackendFactory) -> BackendFactory:
            if key in cls._backends:
                raise ValueError(f"Object storage backend '{key}' is already registered")
            cls._backends[key] = factory
            return factory
        return wrapper

    def __init__(
        self,
        backend: str = "local",
        root: str = ".tm",
        s3_bucket_name: str | None = None,
        s3_root_prefix: str = "",
        s3_region: str = "us-east-1",
        s3_endpoint_url: str | None = None,
        s3_access_key_id: str | None = None,
        s3_secret_access_key: str | None = None,
        s3_allow_http: bool = False,
        s3_path_style: bool = True,
    ):
        if backend not in self._backends:
            raise ValueError(f"Unsupported object storage backend '{backend}'. Expected one of {sorted(self._backends)}.")

        self._backend = backend
        self.root = root
        self.s3_bucket_name = s3_bucket_name
        self.s3_root_prefix = s3_root_prefix
        self.s3_region = s3_region
        self.s3_endpoint_url = s3_endpoint_url
        self.s3_access_key_id = s3_access_key_id
        self.s3_secret_access_key = s3_secret_access_key
        self.s3_allow_http = s3_allow_http
        self.s3_path_style = s3_path_style

        self._resource_repository, self._node_library_repository = self._backends[backend](self)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def resource_repository(self) -> ResourceStorageRepository:
        return self._resource_repository

    @property
    def node_library_repository(self) -> NodeLibraryRepository:
        return self._node_library_repository

@ObjectStorage.register_backend("local")
def _build_local_backend(storage: ObjectStorage) -> tuple[ResourceStorageRepository, NodeLibraryRepository]:
    from ...infrastructure.resource_storage.local_resource_storage_repository import LocalResourceStorageRepository
    from ...infrastructure.node_library.local_node_library_repository import LocalNodeLibraryRepository

    resource_repository = LocalResourceStorageRepository(root=storage.root, namespace=storage.RESOURCE_NAMESPACE)
    node_library_repository = LocalNodeLibraryRepository(root=storage.root, namespace=storage.NODE_LIB_NAMESPACE)
    return resource_repository, node_library_repository

@ObjectStorage.register_backend("s3")
def _build_s3_backend(storage: ObjectStorage) -> tuple[ResourceStorageRepository, NodeLibraryRepository]:
    if not storage.s3_bucket_name:
        raise ValueError("'s3_bucket_name' is required for the 's3' object storage backend")

    from ...infrastructure.resource_storage.s3_resource_storage_repository import S3ResourceStorageRepository
    from ...infrastructure.node_library.s3_node_library_repository import S3NodeLibraryRepository

    resource_repository = S3ResourceStorageRepository(
        bucket_name=storage.s3_bucket_name,
        root_prefix=storage.s3_root_prefix,
        namespace=storage.RESOURCE_NAMESPACE,
        region=storage.s3_region,
        endpoint_url=storage.s3_endpoint_url,
        access_key_id=storage.s3_access_key_id,
        secret_access_key=storage.s3_secret_access_key,
        allow_http=storage.s3_allow_http,
        path_style=storage.s3_path_style,
    )
    node_library_repository = S3NodeLibraryRepository(
        bucket_name=storage.s3_bucket_name,
        root_prefix=storage.s3_root_prefix,
        namespace=storage.NODE_LIB_NAMESPACE,
        region=storage.s3_region,
        endpoint_url=storage.s3_endpoint_url,
        access_key_id=storage.s3_access_key_id,
        secret_access_key=storage.s3_secret_access_key,
        path_style=storage.s3_path_style,
    )
    return resource_repository, node_library_repository
