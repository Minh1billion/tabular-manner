from dataclasses import dataclass

@dataclass(frozen=True)
class CustomNodeDefinition:
    name: str
    description: str
    created_at: str
    expression: str | None = None