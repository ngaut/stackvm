import ast
import operator
import re


class ExpressionEvaluator(ast.NodeVisitor):
    """
    Safely evaluate mathematical expressions.
    """

    # Allowed operators and their corresponding functions
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def visit(self, node):
        """
        Visit a node in the AST.
        """
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        elif isinstance(node, ast.BinOp):
            return self.visit_BinOp(node)
        elif isinstance(node, ast.UnaryOp):
            return self.visit_UnaryOp(node)
        elif isinstance(node, ast.Num):  # For Python versions < 3.8
            return node.n
        elif isinstance(node, ast.Constant):  # For Python versions >= 3.8
            if isinstance(node.value, (int, float)):
                return node.value
            else:
                raise ValueError(f"Unsupported constant: {node.value}")
        else:
            raise TypeError(f"Unsupported node type: {type(node).__name__}")

    def visit_BinOp(self, node):
        """
        Visit a binary operation node.
        """
        left = self.visit(node.left)
        right = self.visit(node.right)
        operator_func = self.operators.get(type(node.op))
        if operator_func is None:
            raise TypeError(f"Unsupported operator: {type(node.op).__name__}")
        return operator_func(left, right)

    def visit_UnaryOp(self, node):
        """
        Visit a unary operation node.
        """
        operand = self.visit(node.operand)
        operator_func = self.operators.get(type(node.op))
        if operator_func is None:
            raise TypeError(f"Unsupported operator: {type(node.op).__name__}")
        return operator_func(operand)


def is_math_expression(text):
    """
    Check if the text is a pure mathematical expression.
    """
    if not isinstance(text, str):
        return False

    # Remove all whitespace
    text_no_space = text.replace(" ", "")

    # Regular expression pattern to match a mathematical expression
    pattern = r"^(?=.*[-+*/().%])[-+*/().%\d\s]+$"

    # Check if the text matches the pattern
    return re.match(pattern, text_no_space) is not None
