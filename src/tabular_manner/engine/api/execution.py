import threading
import traceback
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Iterator

import polars as pl

from ..application.compiler.graph import ExecutionCancelled, Graph, NodeExecutionError
from ..application.compiler.parser import Parser
from ..application.compiler.validator import Validator
from ..application.nodes.custom_node_service import LibraryService
from ..application.runtime.context_manager import ContextManager
from ..application.nodes.registry import NodeRegistry, NodeRegistryProvider
from ..application.runtime.sandbox import Sandbox
from ..domain.models.plan import Plan

def _event(name: str, **data: Any) -> dict[str, Any]:
    return {"event": name, "ts": datetime.now(timezone.utc).isoformat(), **data}


def _failure_event(exc: Exception) -> dict[str, Any]:
    root = exc.original if isinstance(exc, NodeExecutionError) else exc
    data: dict[str, Any] = {
        "error": str(exc),
        "error_type": type(root).__name__,
        "traceback": traceback.format_exc(),
    }
    if isinstance(exc, NodeExecutionError):
        data["node_id"] = exc.node_id
        data["node_type"] = exc.node_type
    return _event("failed", **data)

def _apply_default_bucket(spec: dict[str, Any], registry: NodeRegistry, bucket: str | None) -> dict[str, Any]:
    if bucket is None:
        return spec

    changed = False
    nodes = []
    for n in spec.get("nodes", []):
        try:
            operator_cls = registry.get(n["type"])
        except KeyError:
            nodes.append(n)
            continue

        binds_storage = "resource_storage" in operator_cls.context and "bucket" in operator_cls.optional
        params = n.get("params", {})
        if binds_storage and "bucket" not in params:
            n = {**n, "params": {**params, "bucket": bucket}}
            changed = True
        nodes.append(n)

    return {**spec, "nodes": nodes} if changed else spec

class Execution:
    def __init__(
        self,
        context_manager: ContextManager,
        registry_provider: NodeRegistryProvider,
        sandbox: Sandbox,
        library_service: LibraryService,
        max_cached_graphs: int = 128,
    ):
        self._context_manager = context_manager
        self._registry_provider = registry_provider
        self._sandbox = sandbox
        self._library_service = library_service
        self._max_cached_graphs = max_cached_graphs
        self._graphs: "OrderedDict[str, Graph]" = OrderedDict()
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def _prepare(self, spec: dict[str, Any], bucket: str | None) -> tuple[NodeRegistry, dict[str, Any]]:
        self._library_service.load_persisted(bucket)
        registry = self._registry_provider.get(bucket)
        spec = _apply_default_bucket(spec, registry, bucket)
        return registry, spec

    def _remember(self, execution_id: str, graph: Graph) -> None:
        with self._lock:
            self._graphs[execution_id] = graph
            self._graphs.move_to_end(execution_id)
            self._cancel_events[execution_id] = threading.Event()
            while len(self._graphs) > self._max_cached_graphs:
                evicted_id, _ = self._graphs.popitem(last=False)
                self._cancel_events.pop(evicted_id, None)

    def _recall(self, execution_id: str) -> Graph | None:
        with self._lock:
            graph = self._graphs.get(execution_id)
            if graph is not None:
                self._graphs.move_to_end(execution_id)
            return graph

    def _cancel_event(self, execution_id: str) -> threading.Event:
        with self._lock:
            return self._cancel_events.setdefault(execution_id, threading.Event())

    def cancel(self, execution_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(execution_id)
            if event is None:
                return False
            event.set()
            return True

    def discard(self, execution_id: str) -> None:
        with self._lock:
            self._graphs.pop(execution_id, None)
            self._cancel_events.pop(execution_id, None)

    def _compile(self, spec: dict[str, Any], bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            registry, spec = self._prepare(spec, bucket)

            yield _event("validating")
            Validator(registry, self._sandbox).validate(spec)

            yield _event("parsing")
            graph = Parser.from_json(spec, registry, self._sandbox)

            execution_id = str(uuid.uuid4())
            self._remember(execution_id, graph)
            yield _event("compiled", data={"execution_id": execution_id, "entries": list(graph.entry_ids), "node_count": len(graph.nodes)})
        except Exception as exc:
            yield _failure_event(exc)

    def validate(self, spec: dict[str, Any], bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            registry, spec = self._prepare(spec, bucket)
            yield _event("validating")
            Validator(registry, self._sandbox).validate(spec)
            yield _event("valid")
        except Exception as exc:
            yield _failure_event(exc)

    def execute(self, execution_id: str | None = None, spec: dict[str, Any] | None = None, bucket: str | None = None) -> Iterator[dict[str, Any]]:
        try:
            if execution_id is None and spec is None:
                raise ValueError("Either 'execution_id' or 'spec' must be provided")

            if execution_id is None:
                for event in self._compile(spec, bucket=bucket):
                    yield event
                    if event["event"] == "failed":
                        return
                    if event["event"] == "compiled":
                        execution_id = event["data"]["execution_id"]

            graph = self._recall(execution_id)
            if graph is None:
                raise ValueError(f"Unknown execution_id '{execution_id}'")

            yield _event("injecting_context")
            self._context_manager.inject(graph.nodes)

            total = len(graph.nodes)
            processed = 0
            leaves: list[dict[str, Any]] = []

            initial_plan = Plan(handle=pl.LazyFrame(), meta={"execution_id": execution_id})
            cancel_event = self._cancel_event(execution_id)

            yield _event("running", total_nodes=total)
            for step in graph.traverse(initial_plan, cancel_event=cancel_event, execution_id=execution_id):
                yield _event("node_started", node_id=step.node_id)

                processed += 1
                yield _event("node_completed", node_id=step.node_id, processed=processed, total=total)

                if step.is_leaf:
                    leaf = {"node_id": step.node_id, "history": list(step.plan.history), "columns": step.plan.handle.collect_schema().names()}
                    leaves.append(leaf)
                    yield _event("leaf_reached", **leaf)

            yield _event("completed", data={"execution_id": execution_id, "leaves": leaves})
        except ExecutionCancelled:
            yield _event("cancelled", data={"execution_id": execution_id})
        except Exception as exc:
            yield _failure_event(exc)