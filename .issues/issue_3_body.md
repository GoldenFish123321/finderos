## 问题描述

`app/mcp/client.py` 中使用 **猴补丁 (monkey-patching)** 方式直接在 `threading.current_thread()` 对象上挂载 `_mcp_context` 属性来传递请求上下文。

```python
# mcp/client.py 第120-127行
def set_mcp_context(**kwargs):
    """设置 MCP 工具调用的上下文信息（线程局部存储）。"""
    import threading
    ctx = getattr(threading.current_thread(), "_mcp_context", {})
    ctx.update(kwargs)
    threading.current_thread()._mcp_context = ctx   # ← 猴补丁线程对象！

def clear_mcp_context():
    """清除 MCP 上下文。"""
    import threading
    threading.current_thread()._mcp_context = {}      # ← 猴补丁线程对象！
```

## 为什么这是问题

1. **Tornado 异步环境下线程复用**：Tornado 的 IOLoop 可能在同一个线程中处理多个协程。如果有协程 A 设置了 `_mcp_context` 但忘记清理，协程 B 在该线程上执行时会污染到协程 A 的上下文
2. **异常路径泄漏**：如果 `set_mcp_context()` 之后、`clear_mcp_context()` 之前发生异常，上下文将残留在线程上
3. **非标准做法**：Python 标准库提供了 `contextvars` 模块（Python 3.7+）专门用于此场景，它天然支持协程隔离
4. **属性名冲突风险**：`_mcp_context` 可能与其他库或未来 CPython 的属性冲突

## 建议修复

用 `contextvars.ContextVar` 替代猴补丁：

```python
import contextvars

_mcp_context_var: contextvars.ContextVar[dict] = contextvars.ContextVar('mcp_context', default={})

def set_mcp_context(**kwargs):
    ctx = _mcp_context_var.get().copy()
    ctx.update(kwargs)
    _mcp_context_var.set(ctx)

def get_mcp_context():
    return _mcp_context_var.get()

def clear_mcp_context():
    _mcp_context_var.set({})
```

`contextvars` 在 `asyncio` 协程切换时会自动隔离上下文，不受线程复用影响。
