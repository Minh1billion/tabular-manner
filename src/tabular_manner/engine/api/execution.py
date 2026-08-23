import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

import polars as pl

from ..application.compiler.graph import Graph, NodeExecutionError
from ..application.compiler.parser import Parser
from ..application.compiler.validator import Validator
from ..application.runtime.context_manager import ContextManager
from ..application.nodes.registry import NodeRegistry
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

class Execution:
    def __init__(self, context_manager: ContextManager, registry: NodeRegistry, sandbox: Sandbox):
        self._context_manager = context_manager
        self._registry = registry
        self._sandbox = sandbox
        self._graphs: dict[str, Graph] = {}

    def compile(self, spec: dict[str, Any]) -> Iterator[dict[str, Any]]:
        try:
            yield _event("validating")
            Validator(self._registry, self._sandbox).validate(spec)

            yield _event("parsing")
            graph = Parser.from_json(spec, self._registry, self._sandbox)

            execution_id = str(uuid.uuid4())
            self._graphs[execution_id] = graph
            yield _event("compiled", data={"execution_id": execution_id, "entries": list(graph.entry_ids), "node_count": len(graph.nodes)})
        except Exception as exc:
            yield _failure_event(exc)

    def execute(self, execution_id: str | None = None, spec: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        try:
            if execution_id is None and spec is None:
                raise ValueError("Either 'execution_id' or 'spec' must be provided")

            if execution_id is None:
                for event in self.compile(spec):
                    yield event
                    if event["event"] == "failed":
                        return
                    if event["event"] == "compiled":
                        execution_id = event["data"]["execution_id"]

            graph = self._graphs.get(execution_id)
            if graph is None:
                raise ValueError(f"Unknown execution_id '{execution_id}'")

            yield _event("injecting_context")
            self._context_manager.inject(graph.nodes)

            total = len(graph.nodes)
            processed = 0
            leaves: list[dict[str, Any]] = []

            initial_plan = Plan(handle=pl.LazyFrame(), meta={"execution_id": execution_id})

            yield _event("running", total_nodes=total)
            try:
                for step in graph.traverse(initial_plan):
                    yield _event("node_started", node_id=step.node_id)

                    processed += 1
                    yield _event("node_completed", node_id=step.node_id, processed=processed, total=total)

                    if step.is_leaf:
                        leaf = {"node_id": step.node_id, "history": list(step.plan.history), "columns": step.plan.handle.collect_schema().names()}
                        leaves.append(leaf)
                        yield _event("leaf_reached", **leaf)
            finally:
                # Drop any DataFrames this execution materialized at switch/if nodes so
                # the MaterialBuffer doesn't accumulate memory across executions.
                self._context_manager.get("material_buffer").clear(scope=execution_id)

            yield _event("completed", data={"execution_id": execution_id, "leaves": leaves})
        except Exception as exc:
            yield _failure_event(exc)