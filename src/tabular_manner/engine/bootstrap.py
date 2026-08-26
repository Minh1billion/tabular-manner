from dataclasses import dataclass

from .api.data_resource import DataResource
from .api.execution import Execution
from .api.node_library import NodeLibrary
from .application.nodes.custom_node_service import LibraryService
from .application.nodes.registry import NodeRegistryProvider
from .application.io.reader_factory import ReaderFactory
from .application.io.writer_factory import WriterFactory
from .application.io.resource_storage import ResourceStorage
from .application.storage.object_storage import ObjectStorage
from .application.runtime.sandbox import Sandbox
from .application.runtime.context_manager import ContextManager

@dataclass(frozen=True)
class Engine:
    data_resource: DataResource
    node_library: NodeLibrary
    execution: Execution
    context_manager: ContextManager
    object_storage: ObjectStorage
    registry_provider: NodeRegistryProvider
    sandbox: Sandbox

def build_engine(
    object_storage: ObjectStorage | None = None,
    reader_factory: ReaderFactory | None = None,
    writer_factory: WriterFactory | None = None,
    storage_root: str = ".tm",
    max_cached_graphs: int = 128,
) -> Engine:
    object_storage = object_storage or ObjectStorage(backend="local", root=storage_root)
    reader_factory = reader_factory or ReaderFactory()
    writer_factory = writer_factory or WriterFactory()

    resource_storage = ResourceStorage(repository=object_storage.resource_repository)

    registry_provider = NodeRegistryProvider()
    sandbox = Sandbox()
    node_library_service = LibraryService(
        repository=object_storage.node_library_repository,
        registry_provider=registry_provider,
        sandbox=sandbox,
    )
    node_library_service.load_persisted()
    node_library = NodeLibrary(service=node_library_service)

    context_manager = ContextManager()
    context_manager.register("resource_storage", resource_storage)
    context_manager.register("reader_factory", reader_factory)
    context_manager.register("writer_factory", writer_factory)

    data_resource = DataResource(resource_storage=resource_storage, reader_factory=reader_factory)
    execution = Execution(
        context_manager=context_manager,
        registry_provider=registry_provider,
        sandbox=sandbox,
        library_service=node_library_service,
        max_cached_graphs=max_cached_graphs,
    )

    return Engine(
        data_resource=data_resource,
        node_library=node_library,
        execution=execution,
        context_manager=context_manager,
        object_storage=object_storage,
        registry_provider=registry_provider,
        sandbox=sandbox,
    )