## 问题描述

项目中有 **5 个独立的 `ThreadPoolExecutor`** 分散在不同模块中，各自管理自己的线程池：

| 位置 | 变量名 | 线程数 | 用途 |
|------|--------|--------|------|
| `app/services/scheduler.py:38` | `self._executor` | 2 | 定时采集 |
| `app/controllers/user_chat.py:41` | `_user_chat_executor` | 8 | AI对话 |
| `app/controllers/admin_employee.py:25` | `_invoke_executor` | 4 | 员工调用 |
| `app/controllers/admin_watch.py:25` | `_watch_deep_executor` | 2 | 瞭望深度采集 |
| `app/controllers/admin_warehouse.py:17` | `_deep_collect_executor` | 2 | 仓库深度采集 |

**总计：5 个线程池，18 个线程。**

## 问题

1. **资源碎片化**：无法统一管理线程资源上限，峰值时可能 18 个线程全部活跃
2. **无法统一监控**：难以追踪哪些操作占用了多少线程
3. **shutdown 分散**：每个线程池各自注册 `atexit.register()` 关闭，容易遗漏
4. **缺乏配置化**：线程数硬编码在各模块中，无法根据部署环境调整
5. **无法设置优先级**：所有任务平等竞争线程资源

## 建议修复

创建统一的全局线程池管理模块（如 `app/services/executor.py`）：

```python
import concurrent.futures
import atexit

_global_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="finderos"
)
atexit.register(_global_executor.shutdown, wait=True)

def get_executor():
    return _global_executor
```

所有模块统一使用 `get_executor()` 获取同一个线程池。如需区分优先级，可使用带优先级的任务队列。
