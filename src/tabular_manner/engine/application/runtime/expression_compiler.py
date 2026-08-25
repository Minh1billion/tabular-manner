import ast
import operator

class ExpressionCompiler:
    BIN_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
    }

    COMPARE_OPS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
    }

    def evaluate(self, expression: str, names: dict[str, object]) -> object:
        tree = ast.parse(expression, mode="eval")
        return self._eval(tree.body, names)

    def _eval(self, node: ast.AST, names: dict[str, object]) -> object:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return names[node.id]
        if isinstance(node, ast.Attribute):
            return getattr(self._eval(node.value, names), node.attr)
        if isinstance(node, ast.Call):
            func = self._eval(node.func, names)
            args = [self._eval(arg, names) for arg in node.args]
            kwargs = {kw.arg: self._eval(kw.value, names) for kw in node.keywords}
            return func(*args, **kwargs)
        if isinstance(node, ast.BinOp):
            return self.BIN_OPS[type(node.op)](self._eval(node.left, names), self._eval(node.right, names))
        if isinstance(node, ast.UnaryOp):
            return not self._eval(node.operand, names)
        if isinstance(node, ast.BoolOp):
            return self._eval_bool_op(node, names)
        if isinstance(node, ast.Compare):
            return self._eval_compare(node, names)
        raise ValueError(f"Unsupported expression syntax: {type(node).__name__}")

    def _eval_bool_op(self, node: ast.BoolOp, names: dict[str, object]) -> object:
        is_and = isinstance(node.op, ast.And)
        result = self._eval(node.values[0], names)
        for value_node in node.values[1:]:
            if is_and and not result:
                return result
            if not is_and and result:
                return result
            result = self._eval(value_node, names)
        return result

    def _eval_compare(self, node: ast.Compare, names: dict[str, object]) -> object:
        left = self._eval(node.left, names)
        result = None
        for op, comparator in zip(node.ops, node.comparators):
            right = self._eval(comparator, names)
            step = self.COMPARE_OPS[type(op)](left, right)
            result = step if result is None else (result and step)
            left = right
        return result
