import re
import shutil
import subprocess

import pytest
from tornado.template import Loader


class _Settings:
    SYSTEM_NAME = "FinderOS"
    DEFAULT_WEATHER_CITY = "成都"


def _static_url(path: str) -> str:
    return "/static/" + path


def _render_chat_template(can_config_model_api: bool = True) -> str:
    return Loader("app/templates").load("user_chat.html").generate(
        title="智能问数",
        settings=_Settings,
        static_url=_static_url,
        app_version="test",
        username="tester",
        models=[{
            "id": 1,
            "name": "测试模型",
            "is_enabled": 1,
            "model_scope": "admin",
            "is_default": 1,
        }],
        selected={"id": 1, "name": "测试模型"},
        conversations=[],
        employees=[],
        can_config_model_api=can_config_model_api,
        xsrf_token="test-token",
    ).decode("utf-8")


def test_user_chat_inline_javascript_has_valid_syntax(tmp_path):
    """聊天页核心脚本必须能解析，否则 sendMessage/onkeydown 会整体失效。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript syntax validation")

    html = _render_chat_template(can_config_model_api=True)
    scripts = re.findall(r"<script(?:[^>]*)>(.*?)</script>", html, flags=re.S)
    assert any("function sendMessage()" in script for script in scripts)

    for index, script in enumerate(scripts):
        if not script.strip():
            continue
        script_path = tmp_path / f"user_chat_inline_{index}.js"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_user_chat_media_onerror_handlers_do_not_break_script_string():
    """回归：卡片 onerror 里不能出现会截断单引号 JS 字符串的错误转义。"""
    html = _render_chat_template(can_config_model_api=True)
    assert "this.alt=\\\\'图片加载失败" not in html
    assert "this.style.display=\\\\'none" not in html
    assert "this.alt=&quot;图片加载失败&quot;" in html
    assert "this.style.display=&quot;none&quot;" in html


def test_clear_shortcut_has_been_removed_from_chat_ui():
    """/clear 功能已移除，聊天页不应再暴露入口或特殊处理。"""
    html = _render_chat_template(can_config_model_api=True)
    assert "/clear" not in html
    assert "clearChatShortcut" not in html
    assert "clearChatView" not in html
    assert 'onclick="setInput(\'/clear\')"' not in html


def test_conversation_delete_has_layui_fallback_and_error_feedback():
    """用户侧删除会话不能只依赖 layui，失败时也要明确提示。"""
    html = _render_chat_template(can_config_model_api=True)
    assert "function confirmAction" in html
    assert "window.confirm(message)" in html
    assert "d.msg || '删除对话失败'" in html
    assert "isSameConversationId(currentConversationId, cid)" in html
    assert "当前对话正在回复，请等待回复完成后再删除" in html
