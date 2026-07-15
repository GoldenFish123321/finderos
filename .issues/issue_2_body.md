## 问题描述

`app/services/collector.py` 中的 `_decompress()` 函数（第68-97行）在 Brotli 解压失败时**静默返回空字节 `b""`**，导致数据静默丢失。

```python
if "br" in enc:
    try:
        import brotli
        return brotli.decompress(data)
    except ImportError:
        logger.error("...brotli 包未安装，无法解压，数据将丢失...")
        return b""          # ← 静默返回空字节！
    except Exception as e:
        logger.error(f"Brotli 解压失败: {e}，数据将丢失")
        return b""          # ← 静默返回空字节！
```

## 具体问题

1. **ImportError 时返回空字节**：如果 `brotli` 包未安装且响应确实是 Brotli 压缩的，调用方收到 `b""` 后无法区分"数据为空"还是"解压失败"
2. **其他异常也返回空字节**：任意 `Exception`（如数据损坏）也静默返回 `b""`
3. **调用方无感知**：`fetch_and_parse()` 调用 `_decompress()` 后不会检查是否数据已丢失，继续用空字节去解析 HTML/JSON，产生无意义的结果

## 对比：gzip 和 deflate 的处理

gzip 和 deflate 解压失败时使用了 `try/except: pass`，最终 `return data`（返回原始数据）。虽然也不理想，但至少不会丢失数据。Brotli 分支却直接抛弃数据。

## 建议修复

1. ImportError 时返回原始数据 `return data`（与 gzip/deflate 行为一致），让调用方继续处理（即使可能是乱码）
2. 其他异常时记录错误但仍返回原始数据
3. 或者：抛出明确的自定义异常，让调用方决定如何处理
