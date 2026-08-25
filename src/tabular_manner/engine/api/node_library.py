from datetime import datetime, timezone
from typing import Any, Iterator

from ..application.nodes.custom_node_service import LibraryService
from ..domain.models.custom_node import CustomNodeDefinition

def _event(name: str, **data: Any) -> dict[str, Any]:
    return {"event": name, "ts": datetime.now(timezone.utc).isoformat(), **data}

def _serialize(definition: CustomNodeDefinition) -> dict[str, Any]:
    return {
        "name": definition.name,
        "description": definition.description,
        "created_at": definition.created_at,
        "expression": definition.expression,
    }

class NodeLibrary:
    def __init__(self, service: LibraryService):
        self._service = service

    def register_transform(
        self, name: str, expression: str, description: str = "", bucket: str | None = None
    ) -> Iterator[dict[str, Any]]:
        try:
            yield _event("validating", node_name=name)
            definition = self._service.register_transform(
                name=name, expression=expression, description=description, bucket=bucket
            )
            yield _event("completed", data=_serialize(definition))
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def unregister_node(self, name: str, bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            yield _event("unregistering", node_name=name)
            self._service.unregister_transform(name, bucket=bucket)
            yield _event("completed", data={"name": name})
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def get_node(self, name: str, bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            yield _event("loading", node_name=name)
            definition = self._service.get_transform(name, bucket=bucket)
            yield _event("completed", data=_serialize(definition))
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def describe_nodes(self, bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            yield _event("listing")
            data = self._service.describe_nodes(bucket=bucket)
            yield _event("completed", data=data)
        except Exception as exc:
            yield _event("failed", error=str(exc))

    def list_nodes(self, bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            yield _event("listing")
            custom = [_serialize(definition) for definition in self._service.list_transforms(bucket=bucket)]
            builtin = self._service.builtin_keys()
            yield _event("completed", data={"builtin": builtin, "custom": custom})
        except Exception as exc:
            yield _event("failed", error=str(exc))