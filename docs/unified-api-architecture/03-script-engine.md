# 脚本执行引擎设计（纯数据转换）

> 主文档：[README.md](./README.md) — 架构总览

---

## 五、脚本执行引擎设计（纯数据转换）

### 5.1 设计目标

- 管理员在 MCP 工具编辑页编写 Python **纯数据转换**脚本
- 脚本**仅接收本地接口返回的数据**（接口管理层已将外部 API 代理为本地接口）
- 脚本**返回字符串**（可以是纯文本或 JSON 字符串）作为 MCP 工具结果，前端按内容自动渲染，直接映射为 MCP `text content`
- 脚本**不能发起任何外部调用**（无 import、无网络、无文件系统）
- **安全沙箱**：基于收紧的 AST 白名单遍历，防止恶意代码
- 执行超时保护（signal.alarm + 递归深度限制）

### 5.2 安全策略：收紧的 AST 白名单

> ⚠️ **为什么不用关键词黑名单**: `.lower()` 字符串匹配可被 Unicode 同形字（全角字符）、
> 零宽字符、`chr()` 拼接、`getattr(__builtins__, '__im' + 'port__')` 等无数方式绕过。
> 必须基于**语法树（AST）**做结构级校验。

由于脚本不再需要发起任何外部调用（接口管理层已代理），AST 白名单可以**更激进地收紧**：

**完全禁止 `import` / `ImportFrom`**。数据已是 Python dict/list，不需要 `json`/`random`/`re` 等模块。随机抽取等逻辑用内置函数（`len`、`sorted`、切片）替代。

**AST 白名单允许的节点类型**（纯数据转换最小集合）：

```python
_ALLOWED_NODES = {
    # 基础结构
    ast.Module, ast.FunctionDef, ast.Return,
    ast.Expr, ast.Call, ast.Name, ast.Load, ast.Store,
    ast.Constant,  # Python 3.8+ (str, int, float, bool, None)
    ast.Dict, ast.List, ast.Tuple, ast.Set,
    ast.DictComp, ast.ListComp,
    # 数据访问
    ast.Subscript, ast.Slice,
    # 控制流
    ast.If, ast.IfExp, ast.For, ast.Break, ast.Continue,
    # 运算符
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    # 属性访问（限制危险属性名）
    ast.Attribute, ast.keyword, ast.arg, ast.arguments,
    # 变量
    ast.Assign, ast.AugAssign, ast.Pass,
    # 字符串格式化（f-string）
    ast.JoinedStr, ast.FormattedValue,
    # 操作符节点
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.Pow, ast.FloorDiv,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Not, ast.Invert, ast.UAdd, ast.USub,
}
```

**严格禁止**：
- ❌ **所有 `import` / `ImportFrom`** — 脚本不需要任何外部模块
- ❌ `ast.Call` 中调用 `exec`/`eval`/`open`/`getattr`/`setattr`/`__import__`
- ❌ 任何 `ast.Attribute` 链上访问 `__class__`/`__bases__`/`__subclasses__`/`__globals__`/`__code__`/`__closure__`
- ❌ `ast.While` — 纯数据处理不需要无限循环（用 `for` 即可）

### 5.3 脚本接口规范

```python
# 脚本必须定义 transform 函数
# 输入: data_sources — list[dict], 按 data_sources 配置顺序传入每个本地接口的返回
# 输出: str（纯文本或 JSON 字符串）— 直接作为 MCP tools/call 的 text content 返回给 LLM

def transform(data_sources):
    """
    Args:
        data_sources: [
            { "success": True, "data": {...} },   # 本地接口1返回
            { "success": True, "data": {...} },   # 本地接口2返回 (如有)
        ]
    Returns:
        str: 返回给 LLM 的文本结果（直接映射为 MCP text content）
    """
    # 用户在此编写纯数据转换逻辑
    pass
```

> **为什么返回 `str` 而不是 `dict`**: MCP 协议的 `tools/call` 返回 `{content: [{type: "text", text: "..."}]}`。
> 返回字符串（纯文本或 JSON）直接填入 `text` 字段，无需再 `json.dumps` 包装。LLM 擅长理解和续写自然语言文本，
> 字符串结果比 JSON 嵌套结构更友好。

### 5.4 脚本执行器（收紧版）

```python
# app/services/script_engine.py (新文件)
"""安全的 Python 脚本执行沙箱 — 纯数据转换，无 import，返回字符串（纯文本或 JSON 字符串）。"""

import ast
import logging
import sys
import signal
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 安全内置函数（纯数据操作，无 I/O）
# ═══════════════════════════════════════════════════════════
_SAFE_BUILTINS = {
    # 基础常量
    "True": True, "False": False, "None": None,
    # 类型转换
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    # 集合/序列操作
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "sorted": sorted, "reversed": reversed,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "any": any, "all": all, "isinstance": isinstance,
    # 字符串（仅格式化，不涉及 I/O）
    "format": format,
    # 输出静默（print 无效）
    "print": lambda *a, **kw: None,
    # 全部危险函数覆写为 None
    "__import__": None, "exec": None, "eval": None,
    "open": None, "compile": None, "globals": None, "locals": None,
    "getattr": None, "setattr": None, "delattr": None,
    "__builtins__": None, "__build_class__": None,
    "map": None, "filter": None,  # 禁止函数式遍历（可用推导式替代）
}

# ═══════════════════════════════════════════════════════════
# AST 白名单（收紧版：禁止 import / While）
# ═══════════════════════════════════════════════════════════
_ALLOWED_NODE_TYPES = {
    ast.Module, ast.FunctionDef, ast.Return,
    ast.Expr, ast.Call, ast.Name, ast.Load, ast.Store, ast.Del,
    ast.Constant, ast.Dict, ast.List, ast.Tuple, ast.Set,
    ast.DictComp, ast.ListComp,
    ast.Subscript, ast.Slice,
    ast.If, ast.IfExp, ast.For, ast.Break, ast.Continue,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Attribute, ast.keyword, ast.arg, ast.arguments,
    ast.Assign, ast.AugAssign, ast.Pass,
    ast.JoinedStr, ast.FormattedValue,
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
    ast.Pow, ast.FloorDiv,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.Not, ast.Invert, ast.UAdd, ast.USub,
}

_FORBIDDEN_ATTR_NAMES = {
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__code__", "__closure__", "__func__", "__self__",
    "__builtins__", "__builtin__", "__import__",
}
_FORBIDDEN_CALL_NAMES = {
    "exec", "eval", "open", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "__import__",
}


class ScriptSecurityError(Exception):
    """脚本安全检查未通过。"""
    pass


def _check_ast_node(node: ast.AST):
    """递归遍历 AST 节点，检查是否在白名单内。"""
    if type(node) not in _ALLOWED_NODE_TYPES:
        raise ScriptSecurityError(
            f"不允许的语法节点: {type(node).__name__} (行 {getattr(node, 'lineno', '?')})"
        )

    # 禁止所有 import
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        raise ScriptSecurityError("脚本不允许 import 任何模块")

    # 禁止 While 循环
    if isinstance(node, ast.While):
        raise ScriptSecurityError("脚本不允许使用 while 循环（用 for 替代）")

    # 检查 Call — 禁止调用 exec/eval/open 等
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALL_NAMES:
                raise ScriptSecurityError(f"不允许调用函数: {node.func.id}")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_NAMES:
                raise ScriptSecurityError(f"不允许调用方法: {node.func.attr}")

    # 检查 Attribute — 禁止访问危险属性
    if isinstance(node, ast.Attribute):
        if node.attr in _FORBIDDEN_ATTR_NAMES:
            raise ScriptSecurityError(f"不允许访问属性: {node.attr}")

    for child in ast.iter_child_nodes(node):
        _check_ast_node(child)


def validate_script(script: str) -> Tuple[bool, str]:
    """预检脚本安全性（AST 级）。返回 (is_safe, error_message)。"""
    if not script or not script.strip():
        return True, ""

    # 1. 语法检查
    try:
        tree = ast.parse(script, filename="<script>")
    except SyntaxError as e:
        return False, f"脚本语法错误: 行 {e.lineno} — {e.msg}"

    # 2. AST 白名单遍历
    try:
        _check_ast_node(tree)
    except ScriptSecurityError as e:
        return False, str(e)

    # 3. 检查必须定义 transform 函数
    has_transform = any(
        isinstance(node, ast.FunctionDef) and node.name == "transform"
        for node in ast.walk(tree)
    )
    if not has_transform:
        return False, "脚本必须定义 transform(data_sources) 函数"

    return True, ""


def execute_transform_script(script: str, data_sources: list,
                             timeout: float = 3.0) -> str:
    """在受限环境中执行转换脚本。

    Args:
        script: Python 脚本字符串
        data_sources: 本地接口数据源返回列表
        timeout: 最大执行时间（秒），默认 3s（纯数据转换很快）

    Returns:
        str — 转换后的文本结果（直接作为 MCP text content）
    """
    is_safe, error = validate_script(script)
    if not is_safe:
        return f"[脚本验证失败] {error}"

    sys.setrecursionlimit(200)  # 数据转换递归深度限制更严格

    try:
        restricted_globals = dict(_SAFE_BUILTINS)
        compiled = compile(script, "<script>", "exec")
        exec(compiled, restricted_globals)

        transform_func = restricted_globals.get("transform")
        if not callable(transform_func):
            return "[脚本错误] 未定义有效的 transform 函数"

        def _run():
            return transform_func(data_sources)

        # 超时保护
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(
                signal.SIGALRM,
                lambda *_: (_ for _ in ()).throw(TimeoutError("脚本执行超时"))
            )
            signal.setitimer(signal.ITIMER_REAL, timeout)
            try:
                result = _run()
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            result = _run()

        # 确保返回字符串
        if not isinstance(result, str):
            result = str(result)

        return result

    except TimeoutError:
        return f"[脚本超时] 执行超过 {timeout} 秒"
    except Exception as e:
        logger.error(f"脚本执行失败: {e}", exc_info=True)
        return f"[脚本错误] {str(e)}"
```

> **设计要点**：约 130 行代码。不设 `import` 白名单（脚本无需任何模块）。
> 内置函数限定为纯数据类型转换和集合操作。递归深度限制 200，超时 3 秒。
> 返回值统一为 `str`（纯文本或 JSON 字符串），直接映射到 MCP text content。

### 5.5 脚本示例

#### 示例 1: 天气格式化（单个代理接口 + 纯格式化）

```python
# data_sources: [代理接口 "天气API" → safe_http_request → 外部天气服务]
# 脚本只看到本地接口返回的 dict，完全感知不到外网
def transform(data_sources):
    w = data_sources[0]["data"]["current"]
    return f"{w['city']}今天{w['desc']}，温度{w['temp']}℃，湿度{w['humidity']}%，{w['wind']}"
```

#### 示例 2: 数据仓库概览（多个本地接口 + 文本组合）

```python
# data_sources: [warehouse/stats, warehouse/recent]
# 脚本纯本地数据拼接，无 import、无外网
def transform(data_sources):
    stats = data_sources[0]["data"]
    recent = data_sources[1]["data"].get("items", [])

    lines = [
        f"数据仓库概览：",
        f"· 总记录数: {stats.get('total', 0)}",
        f"· 深度采集: {stats.get('deep_collected', 0)}",
        f"· TOP 来源: {', '.join(stats.get('top_sources', [])[:5])}",
        f"",
        f"最近更新:",
    ]
    for item in recent[:5]:
        lines.append(f"· {item.get('title', '无标题')} ({item.get('source_name', '未知')})")

    return "\n".join(lines)
```

#### 示例 3: 随机音乐（代理接口 + 内置随机抽取，无 import）

```python
# data_sources: [代理接口 "网易云热歌榜" → safe_http_request → api.injahow.cn]
# 不使用 import random，改用 hash + 取模实现伪随机抽取
def transform(data_sources):
    songs = data_sources[0].get("data", [])
    if not songs:
        return "暂无歌曲推荐"

    # 用 len 和 id 组合做伪随机（无需 import random）
    idx = sum(ord(c) for c in songs[0].get("name", "")) % len(songs)
    song = songs[idx]

    return f"🎵 推荐歌曲: {song.get('name', '未知')} — {song.get('artist', '未知')}\n来源: 网易云音乐热歌榜"
```

> **注意**: 示例 3 中脚本不需要也没有 `import random`——AST 白名单禁止所有 import。
> 伪随机用 `hash` 或字符编码求和取模替代。如果确实需要真随机，可在 `_SAFE_BUILTINS` 中注入
> `"random_choice": lambda seq: random.choice(seq)`（预先导入好 `random`，不暴露 `import`）。

---

> 相关文档：[本地接口层设计](./02-local-api-layer.md) | [MCP 注册中心改造](./04-mcp-registry-refactor.md)
