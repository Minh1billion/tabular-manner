import ast

_ALLOWED_AST_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Attribute, ast.Name, ast.Load, ast.Constant, ast.Call,
)

_DEFAULT_ALLOWED_PL_ATTRS = frozenset({"col", "lit", "when"})

_DEFAULT_ALLOWED_NAMES = frozenset({"df", "pl"})

_DEFAULT_SERVICE_CALLS: dict[str, frozenset[str]] = {
    "resource_storage": frozenset({"save", "load", "list"}),
    "reader_factory": frozenset({"read"}),
    "writer_factory": frozenset({"write"}),
}

class Sandbox:
    def __init__(
        self,
        allowed_pl_attrs: frozenset[str] = _DEFAULT_ALLOWED_PL_ATTRS,
        service_calls: dict[str, frozenset[str]] | None = None,
    ):
        self.allowed_pl_attrs = allowed_pl_attrs
        self.service_calls = service_calls if service_calls is not None else dict(_DEFAULT_SERVICE_CALLS)

    def check_expression(self, expression: str, allowed_names: frozenset[str] = _DEFAULT_ALLOWED_NAMES) -> None:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError("Invalid or disallowed expression") from exc

        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_AST_NODES):
                raise ValueError(f"Disallowed expression syntax: {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id not in allowed_names:
                raise ValueError(f"Unknown identifier '{node.id}' in expression")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                raise ValueError(f"Disallowed attribute access '{node.attr}' in expression")
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "pl":
                if node.attr not in self.allowed_pl_attrs:
                    raise ValueError(f"Disallowed attribute access 'pl.{node.attr}' in expression")
            if isinstance(node, ast.Call) and not isinstance(node.func, ast.Attribute):
                raise ValueError("Calls must be method/function calls via attribute access")

    def check_service_call(self, service: str, method: str) -> None:
        allowed_methods = self.service_calls.get(service)
        if allowed_methods is None:
            raise ValueError(f"Service '{service}' is not available for custom actions")
        if method not in allowed_methods:
            raise ValueError(f"Method '{method}' is not allowed on service '{service}'")
