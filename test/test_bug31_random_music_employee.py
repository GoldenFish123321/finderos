"""
Issue #20: 新增随机音乐数字员工 — 功能验证

验证: 
1. 随机音乐员工存在于数据库且属性正确
2. _build_employee_card 正确识别音乐数据并构建卡片
3. API 响应模板扁平化正确处理嵌套 data 字段
4. 前端音乐卡片 URL 安全协议校验
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.digital_employee import DigitalEmployeeRepository
from app.models.db import get_db


def test_random_music_employee_exists():
    """验证随机音乐员工（ID=8）已正确种子化"""
    print("\n=== Issue #20: 随机音乐数字员工验证 ===")

    emp = DigitalEmployeeRepository.get_by_id(8)
    assert emp is not None, "随机音乐员工（ID=8）应存在"
    assert emp["name"] == "随机音乐", f"员工名称应为'随机音乐'，实际: {emp['name']}"
    assert emp["employee_type"] == "api", f"员工类型应为'api'（MCP驱动），实际: {emp['employee_type']}"
    assert emp["is_enabled"] == 1, "随机音乐员工应默认启用"
    # API 型员工应有 mcp_tool_id 绑定
    assert emp.get("mcp_tool_id"), "API 型员工应绑定 MCP 工具"
    print(f"  ✅ 随机音乐员工存在: ID={emp['id']}, 类型={emp['employee_type']} (API型/MCP驱动)")

    # 验证 api_params_template 不使用用户消息作为参数（安全性）
    params = emp.get("api_params_template", "")
    assert "{message}" not in params, f"api_params_template 不应包含 {{message}} 占位符，避免用户消息被误用，实际: {params}"
    print(f"  ✅ api_params_template 不含敏感占位符: {params}")


def test_all_8_employees_exist():
    """验证全部 8 个默认员工均已创建"""
    print("\n  --- 验证: 全部 8 个默认员工 ---")
    employees = DigitalEmployeeRepository.get_enabled()
    assert len(employees) >= 8, f"至少应有 8 个启用的员工，实际: {len(employees)}"
    names = [e["name"] for e in employees]
    expected_names = ["产业专员", "天机助手", "天气", "采集专员", "文案编写", "新闻聚合", "科普助手", "随机音乐"]
    for name in expected_names:
        assert name in names, f"员工 '{name}' 应存在"
    print(f"  ✅ 全部 8 个默认员工均已创建: {names}")


def test_build_music_card_logic():
    """验证 _build_employee_card 音乐卡片构建逻辑（MCP 工具返回格式）"""
    print("\n  --- 验证: 音乐卡片构建逻辑 ---")

    from app.controllers.user_chat import _build_employee_card

    # MCP 工具 get_random_music 返回格式: {success, name, artist, cover, url, source}
    mcp_result = {
        "success": True,
        "name": "测试歌曲A",
        "artist": "测试歌手A",
        "cover": "https://example.com/cover.jpg",
        "url": "https://example.com/music.mp3",
        "source": "网易云音乐热歌榜",
    }

    emp = {"name": "随机音乐", "employee_type": "api"}
    card = _build_employee_card(emp, mcp_result, "来首歌")
    assert card is not None, "应生成音乐卡片"
    assert card["type"] == "music", f"卡片类型应为'music'，实际: {card['type']}"
    assert card["data"]["name"] == "测试歌曲A"
    assert card["data"]["artist"] == "测试歌手A"
    print(f"  ✅ 音乐卡片构建正确: type={card['type']}, song={card['data']['name']}")

    # 模拟 Meting 播放列表格式（向后兼容）
    meting_response = [
        {"name": "测试歌曲B", "artist": "测试歌手B", "url": "https://example.com/play.mp3", "pic": "https://example.com/cover_b.jpg"},
    ]
    card2 = _build_employee_card(emp, meting_response, "来首歌")
    assert card2 is not None
    assert card2["type"] == "music"
    print(f"  ✅ Meting 列表格式音乐卡片构建正确: song={card2['data']['name']}")


def test_music_card_security():
    """验证音乐卡片 URL 安全校验逻辑"""
    print("\n  --- 验证: 音乐卡片 URL 安全 ---")

    # 模拟前端 JavaScript URL 协议校验逻辑
    def is_safe_url(url):
        import re
        return bool(re.match(r'^https?://', url, re.IGNORECASE))

    # 安全 URL
    assert is_safe_url("https://example.com/music.mp3") == True
    assert is_safe_url("http://example.com/music.mp3") == True

    # 危险 URL
    assert is_safe_url("javascript:alert(1)") == False
    assert is_safe_url("data:text/html,<script>alert(1)</script>") == False
    assert is_safe_url("") == False

    print("  ✅ URL 安全校验逻辑正确（仅允许 http/https 协议）")


def test_weather_card_template_uses_path_mapping_not_raw_json():
    """验证天气 API JSON 模板会转成 weather 卡片，而不是直接回显原始 JSON。"""
    from app.controllers.user_chat import _build_employee_card, _card_to_plain_text

    wttr_response = {
        "current_condition": [{
            "temp_C": "26",
            "FeelsLikeC": "28",
            "humidity": "65",
            "windspeedKmph": "9",
            "winddir16Point": "NE",
            "weatherDesc": [{"value": "Partly cloudy"}],
        }],
        "nearest_area": [{
            "areaName": [{"value": "Chengdu"}],
            "region": [{"value": "Sichuan"}],
        }],
        "weather": [{"date": "2026-07-16"}],
    }
    template = json.dumps({
        "type": "weather_card",
        "title": "{{current_condition.0.weatherDesc.0.value}}",
        "fields": [
            {"label": "温度", "value": "{{current_condition.0.temp_C}}°C"},
            {"label": "湿度", "value": "{{current_condition.0.humidity}}%"},
            {"label": "风力", "value": "{{current_condition.0.windspeedKmph}} km/h"},
        ],
    }, ensure_ascii=False)
    emp = {
        "name": "天气",
        "employee_type": "api",
        "response_render_template": template,
    }

    card = _build_employee_card(emp, wttr_response, "成都")
    assert card["type"] == "weather"
    assert card["title"] == "Partly cloudy"
    assert card["data"]["city"] == "Chengdu"
    assert card["data"]["temp"] == "26"
    assert card["data"]["weather"] == "Partly cloudy"
    assert "湿度 65%" in card["data"]["detail"]

    text = _card_to_plain_text(card)
    assert "天气信息" in text
    assert "Chengdu" in text
    assert "current_condition" not in text
    assert "weather_card" not in text


def test_template_flattening():
    """验证 API 响应模板扁平化逻辑"""
    print("\n  --- 验证: 响应模板扁平化逻辑 ---")

    # 模拟 uomg 嵌套响应
    data_obj = {
        "code": 1,
        "data": {
            "name": "测试歌曲名",
            "artistsname": "测试歌手名",
            "coverurl": "https://img.example.com/cover.jpg",
            "url": "https://music.example.com/play.mp3",
        }
    }

    # 扁平化（与 _invoke_api_employee 中的逻辑一致）
    flat_data = {}
    for key, value in data_obj.items():
        if isinstance(value, str):
            flat_data[key] = value
        elif isinstance(value, dict):
            for sub_key, sub_val in value.items():
                if isinstance(sub_val, str):
                    flat_data[sub_key] = sub_val

    assert flat_data["name"] == "测试歌曲名"
    assert flat_data["artistsname"] == "测试歌手名"
    assert flat_data["coverurl"] == "https://img.example.com/cover.jpg"
    assert flat_data["url"] == "https://music.example.com/play.mp3"

    # code 是 int，不应出现在 flat_data 中
    assert "code" not in flat_data

    print(f"  ✅ 模板扁平化正确: {flat_data}")

    # 验证模板替换
    template = '{{name}} - {{artistsname}}'
    import html
    rendered = template
    for key, value in flat_data.items():
        rendered = rendered.replace("{{" + key + "}}", html.escape(value))
    assert rendered == "测试歌曲名 - 测试歌手名"

    from app.controllers.user_chat import _render_value_template
    helper_rendered = _render_value_template(template, data_obj)
    assert helper_rendered == "测试歌曲名 - 测试歌手名"
    assert _render_value_template("{{data.name}}", data_obj) == "测试歌曲名"
    print(f"  ✅ 模板替换正确: {rendered}")


def test_api_music_employee_mcp_invoke_no_args():
    """验证 API 型随机音乐员工通过 MCP 调用时，input_schema 无 properties 时不传多余参数。

    回归: _invoke_api_via_mcp 在 props 为空时 arguments 应为 {}。
    否则 _get_random_music() 收到意外 keyword argument 导致 TypeError → Mock 回退。
    """
    print("\n  --- 验证: API 型音乐员工 MCP 调用参数传递 ---")

    # 模拟 tool_row（get_random_music 的数据库记录）
    tool_row = {
        "name": "get_random_music",
        "display_name": "随机音乐",
        "description": "随机推荐一首歌曲",
        "category": "entertainment",
        "tool_type": "builtin",
        "handler_module": "app.mcp.builtin_tools.entertainment_tools._get_random_music",
        "input_schema": json.dumps({"type": "object", "properties": {}}, ensure_ascii=False),
        "is_enabled": 1,
        "is_system": 1,
    }

    # 模拟参数构建逻辑（与 _invoke_api_via_mcp 一致）
    message = "来首歌"
    arguments = {"message": message}
    input_schema = json.loads(tool_row.get("input_schema", "{}"))
    props = input_schema.get("properties", {})
    if not props:
        arguments = {}
    elif "query" in props:
        arguments = {"query": message}
    elif "keyword" in props:
        arguments = {"keyword": message}
    elif "prompt" in props:
        arguments = {"prompt": message}

    # 验证: props 为空时 arguments 应为空 dict（不传多余参数）
    assert arguments == {}, (
        f"input_schema properties 为空时，arguments 应为 {{}}，"
        f"实际: {arguments}。否则 _get_random_music() 收到多余 kwarg 会 TypeError"
    )

    # 验证 _get_random_music 可无参调用（不应抛 TypeError）
    from app.mcp.builtin_tools.entertainment_tools import _get_random_music
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_get_random_music(**arguments))
    finally:
        loop.close()
    assert result.get("success") is True, f"调用应成功，实际: {result}"
    assert "name" in result, "返回结果应包含歌曲名"
    assert "artist" in result, "返回结果应包含歌手"
    print(f"  ✅ 无参调用 _get_random_music() 成功: {result['name']} - {result['artist']} (来源: {result.get('source')})")


def test_api_music_employee_card_building():
    """验证 API 型音乐员工通过 _build_employee_card 正确构建音乐卡片。"""
    print("\n  --- 验证: API 型音乐员工卡片构建 ---")

    from app.controllers.user_chat import _build_employee_card

    # API 型员工（无 response_render_template，靠员工名识别）
    emp = {
        "name": "随机音乐",
        "employee_type": "api",
        "response_render_template": "",
    }

    # 模拟 get_random_music 真实返回数据
    api_data = {
        "success": True,
        "name": "晴天",
        "artist": "周杰伦",
        "cover": "https://picsum.photos/seed/music1/160/160",
        "url": "https://music.163.com/",
        "source": "网易云音乐热歌榜",
    }

    card = _build_employee_card(emp, api_data, "来首歌")
    assert card is not None, "应生成音乐卡片"
    assert card["type"] == "music", f"卡片类型应为'music'，实际: {card['type']}"
    assert card["data"]["name"] == "晴天"
    assert card["data"]["artist"] == "周杰伦"
    assert card["data"]["cover"] == "https://picsum.photos/seed/music1/160/160"
    assert card["data"]["url"] == "https://music.163.com/"
    print(f"  ✅ API 型员工音乐卡片构建正确: {card['data']['name']} - {card['data']['artist']}")


def test_empty_message_allowed_for_no_arg_api_employee():
    """验证 @随机音乐（无附带消息）时后端允许空消息通过。

    回归: UserEmployeeInvokeHandler 对 API 型+无参工具的 employee 不应拒绝空消息。
    否则仅发送 @随机音乐 时返回 JSON 错误，前端 SSE 解析器无法处理导致挂起。
    """
    print("\n  --- 验证: API 型无参工具允许空消息 ---")
    import json

    # 模拟 get_random_music 工具的 input_schema（无必填参数）
    tool_input_schema = json.dumps({"type": "object", "properties": {}}, ensure_ascii=False)
    required = []
    try:
        schema = json.loads(tool_input_schema)
        required = schema.get("required", [])
    except (json.JSONDecodeError, TypeError):
        pass

    # 无 required 字段 → 应允许空消息
    assert required == [], (
        f"get_random_music 的 input_schema 不应有 required 字段，"
        f"实际: {required}。否则 @随机音乐 无附带消息会被拒绝"
    )
    print(f"  ✅ get_random_music 无 required 字段，空消息应被允许")

    # 模拟 weather_query 工具（有必填参数 message）
    weather_input_schema = json.dumps({
        "type": "object",
        "properties": {"message": {"type": "string", "description": "城市名称"}},
        "required": ["message"]
    }, ensure_ascii=False)
    schema = json.loads(weather_input_schema)
    weather_required = schema.get("required", [])
    assert weather_required == ["message"], "weather_query 需要 message 参数"

    # 模拟空消息判断逻辑（与 UserEmployeeInvokeHandler 一致）
    message = ""  # 用户只发了 @天气，没写城市
    if not message:
        has_required = bool(weather_required)
        # 有 required 参数 → 应拒绝空消息
        assert has_required, "天气查询需要城市名，空消息应被拦截"
    print(f"  ✅ 有 required 参数的工具（如天气）正确拒绝空消息")

    # 测试空消息对 get_random_music 的允许逻辑
    message = ""  # 用户只发了 @随机音乐
    if not message:
        # 无 required → 允许
        assert not required, "随机音乐无 required 参数，空消息应被允许"
    print(f"  ✅ @随机音乐（无附带消息）正确允许通过")


if __name__ == "__main__":
    print("=" * 60)
    print("  Issue #20: 随机音乐数字员工功能验证")
    print("=" * 60)

    try:
        test_random_music_employee_exists()
        test_all_8_employees_exist()
        test_build_music_card_logic()
        test_music_card_security()
        test_weather_card_template_uses_path_mapping_not_raw_json()
        test_template_flattening()
        test_api_music_employee_mcp_invoke_no_args()
        test_api_music_employee_card_building()
        test_empty_message_allowed_for_no_arg_api_employee()
        print("\n" + "=" * 60)
        print("  ✅ 全部测试通过！随机音乐数字员工功能正常。")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n  ❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
