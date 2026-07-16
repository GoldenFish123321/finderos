# AI Prompt 模板

本目录存放 FinderOS 系统使用的 AI 提示词（prompt）模板文件。

## 目录结构

```
docs/prompts/
├── README.md                      # 本文件
├── system_identity.txt            # 系统身份定位
├── chart_instruction.txt          # 图表生成指令
├── tool_usage_instruction.txt     # 工具使用指南
├── media_instruction.txt          # 多模态生成指令
├── employees/                     # 数字员工 system prompt
│   ├── industry_analyst.txt       # 产业专员
│   ├── tianji_assistant.txt       # 天机助手
│   ├── collector.txt              # 采集专员
│   ├── copywriter.txt             # 文案编写
│   ├── news_aggregator.txt        # 新闻聚合
│   └── science_pop.txt            # 科普助手
└── skills/                        # 技能 prompt 模板
    ├── data_stats.txt             # 数据统计
    ├── data_search.txt            # 数据搜索
    ├── news_summary.txt           # 新闻摘要
    ├── deep_collect.txt           # 深度采集
    ├── translation.txt            # 翻译助手
    ├── industry_analysis.txt      # 产业分析
    ├── policy_interpretation.txt  # 政策解读
    ├── competitive_analysis.txt   # 竞品分析
    ├── trend_prediction.txt       # 趋势预判
    ├── copywriting.txt            # 文案撰写
    ├── code_assist.txt            # 代码辅助
    ├── encyclopedia.txt           # 百科问答
    ├── info_retrieval.txt         # 信息检索
    └── data_analysis.txt          # 数据分析
```

## 加载方式

- `app/controllers/user_chat.py` — 通过 `_load_prompt()` 在模块加载时读取 4 个 system prompt
- `app/models/db.py` — 通过 `_load_prompt_file()` 在数据库初始化时读取员工和技能 prompt

## 修改 Prompt

直接编辑对应的 `.txt` 文件，重启服务即可生效（无需修改代码）。

- 文件编码必须为 UTF-8
- 文件缺失时服务会报明确的 RuntimeError，包含缺失文件的完整路径
- 修改后请运行 `python3 -m unittest test.test_skill.TestPromptFileLoading -v` 验证