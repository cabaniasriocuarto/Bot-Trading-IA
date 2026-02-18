from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lark import Lark, Token, Transformer, Tree


ALLOWED_FUNCTIONS = {
    "EMA",
    "RSI",
    "ATR",
    "ADX",
    "CLOSE",
    "OPEN",
    "HIGH",
    "LOW",
    "VOLUME",
    "SPREAD_BPS",
    "OBI_TOPN",
    "CVD",
    "VPIN_PCTL",
    "TSCAN_TMAX",
    "DIST_TO_EMA",
    "LIQUIDITY_OK",
    "IF_ORDERFLOW_ENABLED",
    "ABS",
    "MIN",
    "MAX",
    "CLAMP",
}


DSL_GRAMMAR = r"""
?start: expr

?expr: expr "or" and_expr         -> or_op
     | and_expr

?and_expr: and_expr "and" not_expr -> and_op
         | not_expr

?not_expr: "not" not_expr         -> not_op
         | comparison

?comparison: arith COMP arith      -> compare
           | arith

?arith: arith "+" term            -> add
      | arith "-" term            -> sub
      | term

?term: term "*" factor            -> mul
     | term "/" factor            -> div
     | factor

?factor: "-" factor               -> neg
       | atom

?atom: NUMBER                      -> number
     | NAME "(" [args] ")"       -> func_call
     | "(" expr ")"

args: expr ("," expr)*

COMP: ">="|"<="|">"|"<"|"=="|"!="

%import common.CNAME -> NAME
%import common.SIGNED_NUMBER -> NUMBER
%import common.WS
%ignore WS
"""


class DSLParseError(ValueError):
    pass


@dataclass(slots=True)
class EvalResult:
    value: bool | float
    failed_checks: list[str]


class _NormalizeNumbers(Transformer):
    def number(self, children: list[Token]) -> float:  # type: ignore[override]
        return float(children[0])


_PARSER = Lark(DSL_GRAMMAR, start="start", parser="lalr", maybe_placeholders=False)
_NORMALIZER = _NormalizeNumbers()


def parse_expression(expression: str) -> Tree:
    try:
        parsed = _PARSER.parse(expression)
    except Exception as exc:  # lark exceptions are implementation-specific
        raise DSLParseError(f"Invalid DSL expression: {expression}") from exc
    return _NORMALIZER.transform(parsed)


def _as_bool(value: bool | float) -> bool:
    if isinstance(value, bool):
        return value
    return bool(value)


def _call_function(name: str, args: list[bool | float], context: dict[str, Any], orderflow_enabled: bool) -> bool | float:
    upper = name.upper()
    if upper not in ALLOWED_FUNCTIONS:
        raise DSLParseError(f"Function not allowed: {name}")

    if upper == "ABS":
        return abs(float(args[0]))
    if upper == "MIN":
        return min(float(a) for a in args)
    if upper == "MAX":
        return max(float(a) for a in args)
    if upper == "CLAMP":
        x, lo, hi = (float(a) for a in args)
        return max(lo, min(hi, x))
    if upper == "IF_ORDERFLOW_ENABLED":
        return True if not orderflow_enabled else _as_bool(args[0])

    fn = context.get(upper)
    if fn is None or not callable(fn):
        raise DSLParseError(f"Missing context function: {upper}")
    return fn(*args)


def _eval_tree(node: Tree | Token | float, context: dict[str, Any], orderflow_enabled: bool) -> bool | float:
    if isinstance(node, float):
        return node
    if isinstance(node, Token):
        if node.type == "NUMBER":
            return float(node.value)
        raise DSLParseError(f"Unexpected token: {node.type}")

    data = node.data
    children = node.children

    if data == "start":
        return _eval_tree(children[0], context, orderflow_enabled)
    if data == "number":
        return float(children[0])
    if data == "or_op":
        return _as_bool(_eval_tree(children[0], context, orderflow_enabled)) or _as_bool(
            _eval_tree(children[1], context, orderflow_enabled)
        )
    if data == "and_op":
        return _as_bool(_eval_tree(children[0], context, orderflow_enabled)) and _as_bool(
            _eval_tree(children[1], context, orderflow_enabled)
        )
    if data == "not_op":
        return not _as_bool(_eval_tree(children[0], context, orderflow_enabled))
    if data == "compare":
        left = _eval_tree(children[0], context, orderflow_enabled)
        op = str(children[1])
        right = _eval_tree(children[2], context, orderflow_enabled)
        if op == ">":
            return float(left) > float(right)
        if op == "<":
            return float(left) < float(right)
        if op == ">=":
            return float(left) >= float(right)
        if op == "<=":
            return float(left) <= float(right)
        if op == "==":
            return float(left) == float(right)
        if op == "!=":
            return float(left) != float(right)
        raise DSLParseError(f"Unsupported operator: {op}")
    if data == "add":
        return float(_eval_tree(children[0], context, orderflow_enabled)) + float(
            _eval_tree(children[1], context, orderflow_enabled)
        )
    if data == "sub":
        return float(_eval_tree(children[0], context, orderflow_enabled)) - float(
            _eval_tree(children[1], context, orderflow_enabled)
        )
    if data == "mul":
        return float(_eval_tree(children[0], context, orderflow_enabled)) * float(
            _eval_tree(children[1], context, orderflow_enabled)
        )
    if data == "div":
        denominator = float(_eval_tree(children[1], context, orderflow_enabled))
        if denominator == 0:
            return 0.0
        return float(_eval_tree(children[0], context, orderflow_enabled)) / denominator
    if data == "neg":
        return -float(_eval_tree(children[0], context, orderflow_enabled))
    if data == "func_call":
        name_token = children[0]
        args = []
        if len(children) > 1:
            args_node = children[1]
            if isinstance(args_node, Tree) and args_node.data == "args":
                args = [_eval_tree(child, context, orderflow_enabled) for child in args_node.children]
            else:
                args = [_eval_tree(args_node, context, orderflow_enabled)]
        return _call_function(str(name_token), args, context, orderflow_enabled)
    if data == "args":
        if len(children) == 1:
            return _eval_tree(children[0], context, orderflow_enabled)
        raise DSLParseError("args node cannot be directly evaluated")

    raise DSLParseError(f"Unsupported AST node: {data}")


def evaluate_expression(expression: str, context: dict[str, Any], orderflow_enabled: bool = True) -> bool | float:
    tree = parse_expression(expression)
    return _eval_tree(tree, context=context, orderflow_enabled=orderflow_enabled)


def evaluate_rule_set(
    rules: dict[str, str],
    context: dict[str, Any],
    orderflow_enabled: bool = True,
) -> EvalResult:
    failed: list[str] = []
    for name, expression in rules.items():
        value = evaluate_expression(expression, context=context, orderflow_enabled=orderflow_enabled)
        if not _as_bool(value):
            failed.append(name)
    return EvalResult(value=len(failed) == 0, failed_checks=failed)
