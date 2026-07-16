# CHANGELOG

## [1.9.8-beta] — 2026-07-17

### 重构

- **提取硬编码 AI prompt 到 docs/prompts/ 文件** (PR #157, commit f5325ad)
  - 24 个 AI prompt（4 system + 6 employee + 14 skill）从 Python 代码中提取到 docs/prompts/ 目录
  - 新增 `docs/prompts/employees/` 和 `docs/prompts/skills/` 子目录分类管理
  - `user_chat.py`: 4 个 system prompt 常量改为 `_load_prompt()` 从文件加载
  - `db.py`: 6 个员工 + 14 个技能 prompt 改为 `_load_prompt_file()` 加载
  - 文件缺失时抛出明确的 `RuntimeError`，包含完整路径，避免静默失败
  - 新增 `app/templates/admin/403.html` 统一 403 错误页面，消除 3 处重复内联 HTML
  - 新增 `TestPromptFileLoading` 测试类（6 个测试），验证文件完整性和加载一致性
  - 新增 `docs/prompts/README.md`，说明目录结构和修改方法

### 改进

- 非开发人员可直接编辑 .txt 文件修改 prompt，无需触碰 Python 代码
- 403 错误页面统一为 Tornado 模板，支持动态 message/link/link_text 参数
