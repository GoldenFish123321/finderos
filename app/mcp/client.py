"""
app/mcp/client.py — MCP Client（进程内直连）

为 AI 对话控制器提供统一的工具调用接口：
1. 将 MCP 工具转换为 OpenAI Function Calling 格式
2. 解析 LLM 返回的 tool_calls 并执行
3. 带退避的智能意图匹配（无 API Key 时的回退方案）
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.mcp.server import MCPServer

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP 客户端 — 进程内直连模式。

    不通过 stdio/SSE 传输层，直接调用 MCP Server 的 Python API。
    这使得工具调用延迟为零，适合单体应用场景。
    """

    def __init__(self, server: Optional[MCPServer] = None):
        self._server = server or MCPServer.get_instance()

    # ── 工具发现 ─────────────────────────────────────────

    def get_openai_tools(self, tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """获取 OpenAI Function Calling 格式的工具列表。

        直接传给 LLM API 的 tools 参数：
        POST /chat/completions
        {
            "tools": [...],
            "tool_choice": "auto"
        }
        """
        return self._server.get_openai_tools(tool_names)

    def list_tools(self) -> List[Dict[str, Any]]:
        """获取 MCP 格式的工具列表。"""
        return self._server.list_tools()

    # ── 工具执行 ─────────────────────────────────────────

    async def execute_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """执行 LLM 返回的单个 tool_call。

        Args:
            tool_call: OpenAI tool_call 对象
                {"id": "call_xxx", "type": "function",
                 "function": {"name": "search_warehouse", "arguments": '{"keyword":"AI"}'}}

        Returns:
            {"tool_call_id": "call_xxx", "role": "tool",
             "content": "..."}
        """
        func_info = tool_call.get("function", {})
        tool_name = func_info.get("name", "")
        arguments_str = func_info.get("arguments", "{}")
        tool_call_id = tool_call.get("id", "")

        try:
            arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
        except json.JSONDecodeError as e:
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"参数解析失败: {str(e)}。请使用合法 JSON 格式。",
            }

        # 注入上下文参数（如当前用户名）
        arguments = self._inject_context(arguments, tool_name)

        try:
            result = await self._server.call_tool(tool_name, arguments)
            content = ""
            if result.get("content"):
                # 提取 text 类型内容
                texts = [c["text"] for c in result["content"] if c.get("type") == "text"]
                content = "\n".join(texts)
            if result.get("isError"):
                content = f"[工具执行出错] {content}"

            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": content,
            }
        except Exception as e:
            logger.error(f"工具执行异常: {tool_name} - {e}", exc_info=True)
            return {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": f"工具执行异常: {str(e)}",
            }

    async def execute_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """批量执行多个 tool_calls。

        Returns:
            OpenAI tool 消息列表，可直接追加到 messages。
        """
        results = []
        for tc in tool_calls:
            result = await self.execute_tool_call(tc)
            results.append(result)
        return results

    def _inject_context(self, arguments: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """为特定工具注入上下文参数。"""
        # 通过线程局部存储获取当前请求上下文
        import threading
        ctx = getattr(threading.current_thread(), "_mcp_context", {})
        if ctx:
            if tool_name == "list_conversations" and "username" not in arguments:
                arguments["username"] = ctx.get("username", "")
        return arguments

    # ── 智能意图匹配（无 API Key 时的回退方案）────────────

    def match_tool_by_query(self, user_message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """基于工具描述和用户查询的智能匹配。

        不使用硬编码关键词，而是利用工具自身的 name + description
        进行语义级匹配。这比旧的关键词方案更灵活、更可扩展。

        Returns:
            (tool_name, arguments) 或 None（无匹配时走通用对话）
        """
        msg_lower = user_message.lower().strip()
        tools = self._server.list_tools()

        # 第一步：精确 URL 模式匹配
        url_match = re.search(r'https?://[^\s]{5,}', user_message)
        if url_match:
            url = url_match.group(0)
            # 检查是否要求深度采集
            deep_kw = ["深度采集", "抓取", "提取", "采集这个", "帮我看看这个链接",
                       "fetch", "crawl", "scrape"]
            if any(kw in msg_lower for kw in deep_kw):
                return ("deep_collect_url", {"url": url})

        # 第二步：基于工具名称和描述的评分匹配
        best_score = 0
        best_match = None

        for tool in tools:
            tool_name = tool["name"]
            tool_desc = tool.get("description", "").lower()
            score = self._semantic_score(msg_lower, tool_name, tool_desc)

            if score > best_score and score > 0.3:  # 阈值
                best_score = score
                best_match = tool_name

        if not best_match:
            return None

        # 第三步：提取参数
        arguments = self._extract_arguments(best_match, user_message)

        return (best_match, arguments)

    def _semantic_score(self, query: str, tool_name: str, tool_desc: str) -> float:
        """计算查询与工具的语义匹配分数。

        使用多维度特征：
        1. 工具名中的词是否在查询中出现
        2. 描述中的词是否在查询中出现
        3. 查询意图特征词匹配
        """
        score = 0.0

        # 工具名分词并匹配
        name_parts = re.split(r'[_\-]', tool_name)
        for part in name_parts:
            if part.lower() in query:
                score += 0.25

        # 描述中的特征词匹配
        desc_words = set(re.findall(r'[\u4e00-\u9fff]+|[a-z]+', tool_desc))
        query_words = set(re.findall(r'[\u4e00-\u9fff]+|[a-z]+', query))

        # 中文双字词匹配（更精确）
        for i in range(len(query) - 1):
            bigram = query[i:i + 2]
            if bigram in tool_desc:
                score += 0.05

        # 交集词比例
        if desc_words:
            overlap = desc_words & query_words
            score += len(overlap) / len(desc_words) * 0.3

        return min(score, 1.0)

    def _extract_arguments(self, tool_name: str, message: str) -> Dict[str, Any]:
        """从用户消息中提取工具参数。"""
        args: Dict[str, Any] = {}

        if tool_name == "search_warehouse":
            # 提取搜索关键词：去除意图词和工具名
            kw = self._clean_query_for_keyword(message)
            args["keyword"] = kw
            args["limit"] = 10

        elif tool_name == "get_recent_warehouse_data":
            # 尝试提取数量
            num_match = re.search(r'(\d+)\s*[条个项]', message)
            args["limit"] = int(num_match.group(1)) if num_match else 10

        elif tool_name == "deep_collect_url":
            url_match = re.search(r'https?://[^\s]{5,}', message)
            if url_match:
                args["url"] = url_match.group(0)

        elif tool_name == "collect_web_data":
            kw = self._clean_query_for_keyword(message)
            args["keyword"] = kw

        elif tool_name == "get_conversation_messages":
            id_match = re.search(r'(\d+)', message)
            if id_match:
                args["conversation_id"] = int(id_match.group(1))

        return args

    def _clean_query_for_keyword(self, message: str) -> str:
        """清洗用户消息，提取核心搜索词。"""
        # 移除常见的意图/指令词
        noise_patterns = [
            r'(?:帮我|请|麻烦|能不能|可以|可否)\s*',
            r'(?:搜索|查找|查询|找一下|搜一下|帮我搜|帮我查|帮我找|找)\s*',
            r'(?:一下|一哈|下|哈)\s*',
            r'(?:关于|有关|相关的?|的数据|的内容|的信息)\s*',
            r'(?:有没有|是否有|存在)\s*',
            r'(?:数据仓库|仓库|瞭望)\s*[里中内]?\s*',
            r'(?:最新|最近|近期)\s*',
            r'[？?！!。，,]\s*$',
        ]
        cleaned = message.strip()
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '', cleaned)
        cleaned = cleaned.strip().strip('？?！!。，,').strip()
        return cleaned or message.strip()


# 设置当前请求上下文（在 handler 中调用）
def set_mcp_context(**kwargs):
    """设置 MCP 工具调用的上下文信息（线程局部存储）。"""
    import threading
    ctx = getattr(threading.current_thread(), "_mcp_context", {})
    ctx.update(kwargs)
    threading.current_thread()._mcp_context = ctx


def clear_mcp_context():
    """清除 MCP 上下文。"""
    import threading
    threading.current_thread()._mcp_context = {}
