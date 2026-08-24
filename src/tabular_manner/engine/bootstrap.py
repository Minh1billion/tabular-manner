from dataclasses import dataclass

from .api.data_resource import DataResource
from .api.execution import Execution
from .api.node_library import NodeLibrary
from .application.runtime.context_manager import ContextManager
from .application.nodes.custom_node_service import LibraryService
from .application.nodes.registry import NodeRegistry
from .application.io.reader_factory import ReaderFactory
from .application.storage.resource_storage import ResourceStorage
from .application.runtime.sandbox import Sandbox
from .application.io.writer_factory import WriterFactory
from .application.ports.node_library_repository import NodeLibraryRepository
from .application.ports.resource_storage_repository import ResourceStorageRepository
from .infrastructure.node_library.local_node_library_repository import LocalNodeLibraryRepository
from .infrastructure.resource_storage.local_resource_storage_repository import LocalResourceStorageRepository

@dataclass(frozen=True)
class Engine:
    data_resource: DataResource
    node_library: NodeLibrary
    execution: Execution
    context_manager: ContextManager
    registry: NodeRegistry
    sandbox: Sandbox

def build_engine(
    resource_storage_repository: ResourceStorageRepository | None = None,
    node_library_repository: NodeLibraryRepository | None = None,
    reader_factory: ReaderFactory | None = None,
    writer_factory: WriterFactory | None = None,
    storage_root: str = ".tm/resource_storage",
    node_library_root: str = ".tm/node_library",
    bucket: str | None = None,
) -> Engine:
    resource_storage_repository = resource_storage_repository or LocalResourceStorageRepository(root=storage_root)
    node_library_repository = node_library_repository or LocalNodeLibraryRepository(root=node_library_root)
    reader_factory = reader_factory or ReaderFactory()
    writer_factory = writer_factory or WriterFactory()

    resource_storage = ResourceStorage(repository=resource_storage_repository, bucket=bucket)

    registry = NodeRegistry()
    sandbox = Sandbox()
    node_library_service = LibraryService(repository=node_library_repository, registry=registry, sandbox=sandbox)
    node_library_service.load_persisted()
    node_library = NodeLibrary(service=node_library_service)

    context_manager = ContextManager()
    context_manager.register("resource_storage", resource_storage)
    context_manager.register("reader_factory", reader_factory)
    context_manager.register("writer_factory", writer_factory)

    data_resource = DataResource(resource_storage=resource_storage, reader_factory=reader_factory)
    execution = Execution(context_manager=context_manager, registry=registry, sandbox=sandbox)

    return Engine(
        data_resource=data_resource,
        node_library=node_library,
        execution=execution,
        context_manager=context_manager,
        registry=registry,
        sandbox=sandbox,
    )