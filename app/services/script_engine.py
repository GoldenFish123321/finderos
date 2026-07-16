"""安全脚本执行引擎 — 基于 AST 白名单的 Python 沙箱。

约束:
- 禁用 import/Import/ImportFrom
- 禁用文件 I/O (open/exec/eval/compile)
- 禁用 While 循环（防止无限循环）
- 仅允许有限的内置函数
- 脚本签名: def transform(data_sources: list[dict]) -> str
"""

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 安全的内置函数白名单
_SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "range": range, "enumerate": enumerate, "zip": zip,
    "min": min, "max": max, "sum": sum, "sorted": sorted,
    "abs": abs, "round": round,
    "isinstance": isinstance,
    "print": lambda *a, **kw: None,  # print 静默
    "json": __import__("json"),  # 允许 json
    "re": __import__("re"),      # 允许 re
    "random": __import__("random"),  # 允许 random
}

# AST 节点白名单
_ALLOWED_NODE_TYPES = {
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg,
    ast.Return, ast.Assign, ast.AugAssign,
    ast.Expr, ast.Pass, ast.Break,
    ast.If, ast.For, ast.Try, ast.ExceptHandler, ast.Raise,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Constant, ast.Name, ast.Attribute, ast.Subscript,
    ast.List, ast.Dict, ast.Tuple, ast.Set,
    ast.ListComp, ast.DictComp, ast.SetComp,
    ast.comprehension, ast.Call, ast.Slice, ast.Load, ast.Store,
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Mod, ast.Pow, ast.Eq, ast.NotEq, ast.Lt, ast.Gt,
    ast.LtE, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Not, ast.USub, ast.UAdd,
    ast.FormattedValue, ast.JoinedStr,
}

# 禁用的属性名
_FORBIDDEN_ATTR_NAMES = {
    "__class__", "__bases__", "__subclasses__", "__globals__",
    "__code__", "__builtins__", "__import__",
    "__dict__", "__func__", "__self__", "__call__", "__getattribute__",
    "__mro__", "__base__", "__init__", "__new__",
}

# 禁用的函数调用名
_FORBIDDEN_CALL_NAMES = {"exec", "eval", "compile", "open", "input", "__import__", "getattr", "setattr", "delattr"}


class ScriptSecurityError(Exception):
    """脚本安全校验失败。"""
    pass


def _check_ast_node(node, depth=0, max_depth=50):
    """递归校验 AST 节点的安全性。"""
    if depth > max_depth:
        raise ScriptSecurityError(f"AST 深度超过限制 {max_depth}")

    node_type = type(node)

    # 禁止的节点类型
    if node_type in {ast.Import, ast.ImportFrom}:
        raise ScriptSecurityError(f"禁止 import 语句 (行 {getattr(node, 'lineno', '?')})")
    if node_type is ast.While:
        raise ScriptSecurityError(f"禁止 while 循环 (行 {getattr(node, 'lineno', '?')})")
    if node_type is ast.Global:
        raise ScriptSecurityError(f"禁止 global 声明 (行 {getattr(node, 'lineno', '?')})")
    if node_type is ast.ClassDef:
        raise ScriptSecurityError(f"禁止 class 定义 (行 {getattr(node, 'lineno', '?')})")

    # 未在白名单的节点类型
    if node_type not in _ALLOWED_NODE_TYPES:
        raise ScriptSecurityError(
            f"不安全的语法结构: {node_type.__name__} (行 {getattr(node, 'lineno', '?')})"
        )

    # Attribute: 禁止危险属性
    if isinstance(node, ast.Attribute):
        if node.attr in _FORBIDDEN_ATTR_NAMES:
            raise ScriptSecurityError(
                f"禁止访问属性: {node.attr} (行 {getattr(node, 'lineno', '?')})"
            )

    # Call: 禁止危险函数
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALL_NAMES:
                raise ScriptSecurityError(
                    f"禁止调用函数: {node.func.id} (行 {getattr(node, 'lineno', '?')})"
                )

    # 递归校验子节点
    for child in ast.iter_child_nodes(node):
        _check_ast_node(child, depth + 1, max_depth)


def validate_script(script: str) -> tuple[bool, str]:
    """预检脚本安全性。返回 (is_valid, error_message)。"""
    if not isinstance(script, str):
        return False, "脚本内容必须为字符串"
    try:
        tree = ast.parse(script, mode="exec")
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    try:
        _check_ast_node(tree)
    except ScriptSecurityError as e:
        return False, str(e)

    # 检查是否定义了 transform 函数
    has_transform = any(
        isinstance(node, ast.FunctionDef) and node.name == "transform"
        for node in ast.iter_child_nodes(tree)
    )
    if not has_transform:
        return False, "脚本必须定义 transform(data_sources) 函数"

    return True, ""


def execute_transform_script(script: str, data_sources: list[dict]) -> str:
    """在受限沙箱中执行转换脚本。返回输出字符串。"""
    # 预检
    is_valid, error = validate_script(script)
    if not is_valid:
        logger.warning(f"脚本校验失败: {error}")
        return f"[脚本校验失败] {error}"

    # 编译
    try:
        code = compile(script, "<transform_script>", "exec")
    except SyntaxError as e:
        return f"[编译错误] {e}"

    # 受限执行环境
    restricted_globals = {"__builtins__": _SAFE_BUILTINS}
    restricted_locals = {}

    try:
        exec(code, restricted_globals, restricted_locals)
    except Exception as e:
        logger.error(f"脚本执行异常: {e}", exc_info=True)
        return f"[执行错误] {type(e).__name__}: {e}"

    # 调用 transform 函数
    transform_fn = restricted_locals.get("transform")
    if not callable(transform_fn):
        return "[错误] 未找到 transform 函数"

    try:
        result = transform_fn(data_sources)
    except Exception as e:
        logger.error(f"transform 函数异常: {e}", exc_info=True)
        return f"[转换错误] {type(e).__name__}: {e}"

    return str(result)
