## 问题描述

`app/services/collector.py` 和 `app/services/deep_collector.py` 两个文件中各自独立定义了完全相同的以下代码：

### 重复定义的类/变量

1. **`_NoRedirectHandler` 类** — 两个文件各自定义了完全相同的 SSRF 重定向拦截器
2. **`_ssl_ctx` (SSL上下文)** — 各自创建 `ssl.create_default_context()` 并设置 `maximum_version = TLSv1_2`
3. **`_no_redirect_opener`** — 各自构建不跟随重定向的 urllib opener
4. **`_BASE_HEADERS`** — 完全相同的 Chome 138 User-Agent 请求头字典

### 具体代码对比

**collector.py** (第28-58行):
```python
_global_ssl_ctx = ssl.create_default_context()
_global_ssl_ctx.maximum_version = ssl.TLSVersion.TLSv1_2

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
    http_error_301 = http_error_302 = ... = lambda self, req, fp, code, msg, hdrs: fp

_no_redirect_opener = urllib.request.build_opener(
    _NoRedirectHandler(),
    urllib.request.HTTPSHandler(context=_global_ssl_ctx),
)

_BASE_HEADERS = { "User-Agent": "Mozilla/5.0 ... Chrome/138.0.0.0 Safari/537.36", ... }
```

**deep_collector.py** (第36-64行):
```python
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.maximum_version = ssl.TLSVersion.TLSv1_2

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
    http_error_301 = http_error_302 = ... = lambda self, req, fp, code, msg, hdrs: fp

_no_redirect_opener = urllib.request.build_opener(
    _NoRedirectHandler(),
    urllib.request.HTTPSHandler(context=_ssl_ctx),
)

_BASE_HEADERS = { "User-Agent": "Mozilla/5.0 ... Chrome/138.0.0.0 Safari/537.36", ... }
```

## 影响

- 如果需要修改 TLS 版本限制、User-Agent 或重定向策略，必须同时修改两个文件
- 容易产生不一致：一处改了另一处忘记改
- 违反 DRY (Don't Repeat Yourself) 原则
- 也存在于 `_decompress()` 函数的重复逻辑

## 建议修复

将这些共用代码提取到一个共享模块（如 `app/services/_http_utils.py`），由 `collector.py` 和 `deep_collector.py` 共同导入使用。
