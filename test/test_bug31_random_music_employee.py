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
    assert emp["employee_type"] == "api", f"员工类型应为'api'，实际: {emp['employee_type']}"
    assert emp["is_enabled"] == 1, "随机音乐员工应默认启用"
    assert "api.injahow.cn" in emp.get("api_url", ""), f"API URL 应包含 injahow (Meting API)，实际: {emp['api_url']}"
    print(f"  ✅ 随机音乐员工存在: ID={emp['id']}, 类型={emp['employee_type']}")
    print(f"     API URL: {emp['api_url']}")

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
    """验证 _build_employee_card 音乐卡片构建逻辑"""
    print("\n  --- 验证: 音乐卡片构建逻辑 ---")

    # 导入 _build_employee_card
    from app.controllers.user_chat import _build_employee_card

    # 模拟 uomg API 返回的嵌套数据格式: {code: 1, data: {name, artistsname, coverurl, url}}
    uomg_response = {
        "code": 1,
        "data": {
            "name": "测试歌曲",
            "artistsname": "测试歌手",
            "coverurl": "https://example.com/cover.jpg",
            "url": "https://example.com/music.mp3",
        }
    }

    emp = {"name": "随机音乐", "employee_type": "api", "response_render_template": "{}"}

    card = _build_employee_card(emp, uomg_response, "来首歌")
    assert card is not None, "应生成音乐卡片"
    assert card["type"] == "music", f"卡片类型应为'music'，实际: {card['type']}"
    assert "随机音乐" in card["title"], f"卡片标题应包含'随机音乐'，实际: {card['title']}"
    assert card["data"]["name"] == "测试歌曲", f"歌曲名应为'测试歌曲'，实际: {card['data']['name']}"
    assert card["data"]["artist"] == "测试歌手", f"歌手应为'测试歌手'，实际: {card['data']['artist']}"
    assert card["data"]["cover"] == "https://example.com/cover.jpg"
    assert card["data"]["url"] == "https://example.com/music.mp3"
    print(f"  ✅ 音乐卡片构建正确: type={card['type']}, song={card['data']['name']}")

    # 模拟 Meting 播放列表格式：[{name, artist, url, pic, lrc}, ...]
    meting_response = [
        {"name": "测试歌曲B", "artist": "测试歌手B", "url": "https://example.com/play.mp3", "pic": "https://example.com/cover_b.jpg", "lrc": "..."},
        {"name": "测试歌曲C", "artist": "测试歌手C", "url": "https://example.com/play2.mp3", "pic": "https://example.com/cover_c.jpg", "lrc": "..."},
    ]
    card2 = _build_employee_card(emp, meting_response, "来首歌")
    assert card2 is not None
    assert card2["type"] == "music"
    assert card2["data"]["name"] in ["测试歌曲B", "测试歌曲C"]
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
    print(f"  ✅ 模板替换正确: {rendered}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Issue #20: 随机音乐数字员工功能验证")
    print("=" * 60)

    try:
        test_random_music_employee_exists()
        test_all_8_employees_exist()
        test_build_music_card_logic()
        test_music_card_security()
        test_template_flattening()
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
