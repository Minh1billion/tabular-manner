from dataclasses import dataclass

@dataclass(frozen=True)
class CustomNodeDefinition:
    name: str
    kind: str
    description: str
    created_at: str
    expression: str | None = None
    service: str | None = None
    method: str | None = None
    handle_param: str | None = None