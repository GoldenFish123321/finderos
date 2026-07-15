## 问题描述

`app/services/collector.py` 中的 `_ensure_baidu_cookies()` 函数（第261-308行）在**持有线程锁期间发起阻塞 HTTP 请求**。

```python
def _ensure_baidu_cookies():
    global _global_cookie_jar
    if _global_cookie_jar is not None:
        return

    with _global_cookie_lock:              # ← 获取锁
        if _global_cookie_jar is not None:
            return

        for attempt in range(3):
            # ... 构建 opener ...
            resp = opener.open(req, timeout=15)   # ← 锁内阻塞HTTP请求！
            resp.read()                            # ← 锁内阻塞读取！
            # ...
            time.sleep(wait_sec)                   # ← 锁内sleep！
```

## 为什么是严重问题

1. **锁内阻塞 HTTP 请求**：百度首页可能响应慢（网络延迟、服务器繁忙），`opener.open(req, timeout=15)` 最多等待 15 秒
2. **锁内重试 + sleep**：失败后重试 3 次，每次带有 `time.sleep(2s/4s)` 的指数退避
3. **最坏情况**：15s × 3 次请求 + 2s + 4s sleep = **51 秒**锁持有时间
4. **Tornado 事件循环阻塞**：虽然是线程锁而非 IOLoop 锁，但在 Tornado 的线程池中执行时，如果多个线程同时调用此函数，它们会串行等待锁释放。专用线程只有 2 个（scheduler executor），如果两个都被 `_ensure_baidu_cookies` 占用，整个采集功能将完全阻塞

## 建议修复

将 HTTP 请求移到锁外部，仅在锁内部更新全局变量：

```python
def _ensure_baidu_cookies():
    global _global_cookie_jar
    if _global_cookie_jar is not None:
        return

    # 在锁外执行 HTTP 请求
    cj = _fetch_baidu_cookies_with_retry()

    with _global_cookie_lock:
        if _global_cookie_jar is None:
            _global_cookie_jar = cj
```
