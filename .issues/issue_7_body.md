## 问题描述

`app/services/collector.py` 中的 `parse_baidu_news()` 和 `parse_sogou_news()` 函数使用**纯正则表达式**解析搜索引擎结果页 HTML。

```python
# collector.py parse_baidu_news()
blocks = re.split(r'<div[^>]*class="[^"]*result[^"]*"[^>]*>', html)
# ...
tm = re.search(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
# ...
sm = re.search(r'<(?:span|div|p|em)[^>]*class="[^"]*(?:abstract|summary|content|desc)[^"]*"[^>]*>(.*?)</(?:span|div|p|em)>', block, re.DOTALL)
```

## 为什么极其脆弱

1. **搜索引擎改版即失效**：百度/搜狗前端 HTML 结构和 CSS 类名随时可能变化，一旦改版，整个采集功能立即瘫痪
2. **正则无法处理嵌套 HTML**：如 `<div><div>内容</div></div>` 用正则匹配会出错
3. **反爬页面无法识别**：遇到验证码/人机验证页面时，正则仍尝试匹配，返回空结果但无任何提示
4. **CDN/地区差异**：不同地区/网络环境返回的 HTML 可能有细微差异，导致正则在某些环境生效、某些环境失效
5. **无回退机制**：解析失败时返回空列表，调用方（`fetch_and_parse`）无法知道是"没匹配到"还是"页面结构变了"

## 当前权宜之计

项目在 `parse_baidu_news` 中用 `if len(blocks) <= 1: blocks = re.split(r"<h3[^>]*>", html)` 做回退，但这只是换一个同样脆弱的正则。

## 建议修复

1. 首选：使用结构化 HTML 解析器（`BeautifulSoup4` + `lxml`），按语义结构提取信息
2. 次选：至少对解析结果做健康检查（如返回 0 条时检查 HTML 中是否存在"验证码""404"等异常标识）
3. 可选：引入爬虫框架（如 `crawl4ai` 已在 `requirements.txt` 中作为可选依赖），用于正文提取
