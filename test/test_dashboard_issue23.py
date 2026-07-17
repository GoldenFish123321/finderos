"""
Issue #23 — 管理侧数智大屏（3D地球+词云+数据可视化）

验证内容：
1. Dashboard handler 存在且可导入
2. dashboard.html 模板包含必需的 CDN 和图表容器
3. DataWarehouse 新增统计方法正确
4. 路由和菜单项已注册
5. CSP 已更新允许大屏资源
"""

import os
import sys
import json
import re
import pytest
from types import SimpleNamespace
from tornado.escape import json_encode
from tornado.template import Loader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDashboardHandler:
    """验证 Dashboard Handler"""

    def test_handler_importable(self):
        """admin_home 模块可导入且包含 Dashboard Handler"""
        from app.controllers.admin_home import AdminDashboardHandler, AdminDashboardApiHandler
        assert AdminDashboardHandler is not None
        assert AdminDashboardApiHandler is not None

    def test_handler_inherits_admin_base(self):
        """Dashboard Handler 继承 AdminBaseHandler"""
        from app.controllers.admin_home import AdminDashboardHandler, AdminDashboardApiHandler
        from app.controllers.admin_base import AdminBaseHandler
        assert issubclass(AdminDashboardHandler, AdminBaseHandler)
        assert issubclass(AdminDashboardApiHandler, AdminBaseHandler)

    def test_render_passes_xsrf_token(self):
        """AdminDashboardHandler.get() 的 render 调用包含 xsrf_token"""
        import inspect
        from app.controllers.admin_home import AdminDashboardHandler
        source = inspect.getsource(AdminDashboardHandler.get)
        assert "xsrf_token" in source, (
            "AdminDashboardHandler.get() 的 self.render() 缺少 xsrf_token 参数"
        )


class TestDashboardTemplate:
    """验证 Dashboard 模板"""

    TEMPLATE_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app", "templates", "admin", "dashboard.html"
    )

    def test_template_exists(self):
        """dashbaord.html 文件存在"""
        assert os.path.exists(self.TEMPLATE_PATH), "dashboard.html 不存在"

    def test_three_globe_with_canvas_fallback_no_browser_plugin(self):
        """3D 地球使用 Three.js 数字地球主实现，并保留 Canvas 兜底；不依赖 ECharts-GL 或浏览器插件。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "three@0.132.2" in content, "缺少 Three.js CDN"
        assert "OrbitControls" in content, "缺少 Three.js OrbitControls"
        assert "initThreeGlobe" in content, "缺少 Three.js 数字地球初始化"
        assert "THREE.WebGLRenderer" in content, "Three.js 地球应使用 WebGLRenderer"
        assert "THREE_GLOBE_TEXTURES" in content, "缺少真实地球纹理配置"
        assert "browserSupportsWebGL" in content, "缺少 WebGL 能力检测"
        assert "getDisplayDomain" in content, "缺少演示域名隐藏逻辑"
        assert "markerSize = 1.15 + strength * 2.55" in content, "Three.js 来源点位不应过大"
        assert "glowSize = 7 + strength * 10" in content, "Three.js 来源点位光晕不应过大"
        assert "three-globe-canvas" in content, "缺少 Three.js 地球 Canvas"
        assert "initCanvasGlobe" in content, "缺少原生 Canvas 兜底"
        assert "globe-canvas" in content, "缺少原生 Canvas 地球兜底容器"
        assert "requestAnimationFrame" in content, "原生 3D 地球应具备动画渲染"
        assert "drawSpaceBackdrop" in content, "3D 地球应内置星空背景"
        assert "drawAtmosphereBack" in content, "3D 地球应内置大气辉光"
        assert "drawCloudLayer" in content, "3D 地球应内置云层效果"
        assert "landPolygons" in content, "3D 地球应内置陆地轮廓"
        assert "initCharts();" in content, "3D 地球初始化不能等待外部 ECharts CDN"
        assert "ECharts 加载超时" not in content, "不能因 ECharts 加载失败跳过地球初始化"
        assert "echarts-gl" not in content, "3D 地球不能依赖 echarts-gl CDN"
        assert "echarts-wordcloud" in content, "缺少 echarts-wordcloud CDN"

    def test_all_chart_containers_exist(self):
        """模板包含所有必需的图表容器"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        containers = [
            "chart-globe",      # 3D地球
            "chart-wordcloud",  # 词云
            "chart-trend",      # 趋势
            "chart-source",     # 来源分布
            "chart-deep",       # 深度采集占比
        ]
        for cid in containers:
            assert f'id="{cid}"' in content, f"缺少图表容器 {cid}"

    def test_dashboard_layout_uses_coordinated_grid(self):
        """数智大屏采用主地球、右侧信息宫格和底部等高图表的协调布局。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        required_classes = [
            "dashboard-globe-panel",
            "dashboard-side-grid",
            "dashboard-wordcloud-panel",
            "dashboard-keyword-panel",
            "dashboard-source-panel",
            "dashboard-recent-panel",
            "dash-mini-chart",
        ]
        for cls in required_classes:
            assert cls in content, f"缺少布局类 {cls}"
        assert "grid-template-rows: minmax(190px" in content, "右侧信息区应使用宫格行高"
        assert "display:flex;flex-direction:column;gap:14px" not in content, "不应退回旧的竖直堆叠内联布局"

    def test_stat_cards_exist(self):
        """模板包含统计卡片"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        stats = ["数据总量", "今日新增", "已深度采集", "数据来源"]
        for s in stats:
            assert s in content, f"缺少统计卡片: {s}"

    def test_keyword_ranking_list(self):
        """模板包含关键词排行榜"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "keyword-list" in content, "缺少关键词列表"
        assert "热门关键词" in content, "缺少热门关键词标题"


    def test_template_renders_keyword_ranking_without_jinja_loop(self):
        """回归：Tornado 模板没有 Jinja 的 loop.index，排行榜应能实际渲染。"""
        class _Settings:
            SYSTEM_NAME = "FinderOS"
            SYSTEM_SUBTITLE = "Test"
            SYSTEM_LOGO = ""

        handler = SimpleNamespace(request=SimpleNamespace(path="/admin/dashboard"))
        html = Loader(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "templates", "admin")).load("dashboard.html").generate(
            title="数智大屏",
            username="admin",
            xsrf_token="test-token",
            settings=_Settings,
            app_version="test",
            static_url=lambda path: "/static/" + path,
            admin_can=lambda route: True,
            handler=handler,
            json_encode=json_encode,
            stats={
                "total": 1, "today_count": 1, "deep_collected": 0,
                "deep_pct": 0, "source_count": 1, "top_source": "测试",
            },
            source_distribution=[{"name": "测试", "value": 1}],
            source_geo=[{
                "name": "测试", "value": 1, "deep_count": 0, "today_count": 1,
                "domain": "example.test", "city": "北京", "coord": [116.4, 39.9],
            }],
            trend={"dates": ["2026-07-16"], "counts": [1]},
            keywords=[{"name": "天气", "value": 3}, {"name": "音乐", "value": 2}],
            recent_items=[{
                "title": "测试记录", "source": "测试", "created_at": "2026-07-16",
                "is_deep_collected": 0, "keyword": "天气",
            }],
        ).decode("utf-8")

        assert "rank-1" in html
        assert "天气" in html
        assert "source_geo" in html
        assert "recent_items" in html
        assert "来源点位预览" in html
        assert "最新入库动态" in html
        assert "loop.index" not in html

    def test_dashboard_template_uses_real_source_geo_not_random_points(self):
        """地球点位应来自后端 source_geo，不再按关键词随机生成城市散点。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "source_geo" in content
        assert "renderSourceList" in content
        assert "chart-fallback" in content
        assert "safeChart" in content
        assert "setChartFallback" in content
        assert "Three.js 数字地球" in content
        assert "Canvas 兜底" in content
        assert "根据关键词词频生成数据点密度" not in content
        assert "sourceGeoData" in content

    def test_refresh_button(self):
        """模板包含刷新按钮"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "refreshDashboard" in content, "缺少刷新功能"
        assert "btn-dash-refresh" in content, "缺少刷新按钮"

    def test_chart_init_functions(self):
        """模板包含各图表初始化函数"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        functions = [
            "initGlobe",       # 3D地球
            "initThreeGlobe",  # Three.js数字地球
            "initCanvasGlobe", # Canvas兜底
            "initWordCloud",   # 词云
            "initTrendChart",  # 趋势
            "initSourcePie",   # 来源
            "initDeepPie",     # 深度占比
        ]
        for fn in functions:
            assert fn in content, f"缺少图表初始化函数 {fn}"

    def test_api_refresh_mechanism(self):
        """模板通过 /admin/api/dashboard 刷新数据"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "/admin/api/dashboard" in content, "缺少刷新 API 调用"
        assert "fetch(" in content.split("window.refreshDashboard")[1] if "window.refreshDashboard" in content else "", "刷新应使用 fetch"

    def test_no_js_syntax_errors(self):
        """模板 JS 括号匹配"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # 提取 JS 部分
        js_start = content.rfind("<script>")
        js_end = content.rfind("</script>")
        if js_start >= 0 and js_end > js_start:
            js = content[js_start + 8:js_end]
            opens = js.count("{") + js.count("(") + js.count("[")
            closes = js.count("}") + js.count(")") + js.count("]")
            assert opens == closes, f"JS 括号不匹配: open={opens}, close={closes}"


class TestDataWarehouseStats:
    """验证 DataWarehouse 新增统计方法"""

    def test_new_methods_exist(self):
        """DataWarehouseRepository 包含新增方法"""
        from app.models.data_warehouse import DataWarehouseRepository

        methods = [
            "get_keyword_frequency",
            "get_dashboard_stats",
            "get_trend_data",
            "get_source_distribution",
        ]
        for m_name in methods:
            assert hasattr(DataWarehouseRepository, m_name), f"缺少方法 {m_name}"
            assert callable(getattr(DataWarehouseRepository, m_name)), f"{m_name} 不可调用"

    def test_keyword_frequency_returns_list(self):
        """get_keyword_frequency 返回列表"""
        from app.models.data_warehouse import DataWarehouseRepository
        result = DataWarehouseRepository.get_keyword_frequency(10)
        assert isinstance(result, list)

    def test_dashboard_stats_structure(self):
        """get_dashboard_stats 返回正确结构"""
        from app.models.data_warehouse import DataWarehouseRepository
        stats = DataWarehouseRepository.get_dashboard_stats()
        required_keys = [
            "total", "deep_collected", "today_count", "source_count",
            "top_source", "top_source_count", "enabled_source_count",
            "scheduled_source_count", "success_rate", "avg_response_kb",
            "latest_record_at",
        ]
        for k in required_keys:
            assert k in stats, f"缺少统计字段 {k}"

    def test_dashboard_source_geo_aggregates_real_sources(self):
        """来源地球数据应聚合各种真实来源数量、深采数量和地理标注。"""
        from app.models.db import get_db
        from app.models.data_warehouse import DataWarehouseRepository

        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO watch_results (source_id, keyword, request_url, response_status, response_size) "
                "VALUES (1, '天气', 'https://www.baidu.com/s?word=天气', 200, 2048)"
            )
            result_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO data_warehouse "
                "(result_id, title, link, summary, source_name, is_deep_collected) "
                "VALUES (?, '成都天气新闻', 'https://www.baidu.com/item/1', '天气摘要', '百度新闻', 1)",
                (result_id,),
            )
            cursor = conn.execute(
                "INSERT INTO watch_sources (name, url_template, is_enabled) "
                "VALUES ('GitHub Trending', 'https://github.com/trending/{keyword}', 1)"
            )
            github_source_id = cursor.lastrowid
            cursor = conn.execute(
                "INSERT INTO watch_results (source_id, keyword, request_url, response_status, response_size) "
                "VALUES (?, 'AI', 'https://github.com/trending/python', 200, 4096)",
                (github_source_id,),
            )
            github_result_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO data_warehouse "
                "(result_id, title, link, summary, source_name, is_deep_collected) "
                "VALUES (?, 'GitHub AI 项目趋势', 'https://github.com/example/repo', '开源项目摘要', 'GitHub Trending', 0)",
                (github_result_id,),
            )
            conn.execute(
                "INSERT INTO data_warehouse "
                "(title, link, summary, source_name, is_deep_collected) "
                "VALUES ('自定义接口数据', 'https://custom.example.test/item/1', '自定义来源摘要', '自定义接口源', 0)"
            )

        points = DataWarehouseRepository.get_dashboard_source_geo(5)
        by_name = {p["name"]: p for p in points}
        assert {"百度新闻", "GitHub Trending", "自定义接口源"} <= set(by_name)
        assert by_name["百度新闻"]["value"] == 1
        assert by_name["百度新闻"]["deep_count"] == 1
        assert by_name["百度新闻"]["city"] == "北京"
        assert by_name["GitHub Trending"]["city"] == "San Francisco"
        assert by_name["自定义接口源"]["location_source"] == "fallback"
        assert all(len(p["coord"]) == 2 for p in points)

    def test_trend_data_structure(self):
        """get_trend_data 返回 dates 和 counts"""
        from app.models.data_warehouse import DataWarehouseRepository
        trend = DataWarehouseRepository.get_trend_data(7)
        assert "dates" in trend, "缺少 dates 字段"
        assert "counts" in trend, "缺少 counts 字段"
        assert isinstance(trend["dates"], list)
        assert isinstance(trend["counts"], list)
        assert len(trend["dates"]) == 7, f"应返回7天数据, 实际 {len(trend['dates'])}"

    def test_source_distribution_returns_list(self):
        """get_source_distribution 返回列表格式正确"""
        from app.models.data_warehouse import DataWarehouseRepository
        result = DataWarehouseRepository.get_source_distribution(5)
        assert isinstance(result, list)
        for item in result:
            assert "name" in item
            assert "value" in item


class TestRoutesAndMenu:
    """验证路由和菜单项"""

    def test_routes_registered(self):
        """main.py 包含 Dashboard 路由"""
        main_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "main.py"
        )
        with open(main_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "/admin/dashboard" in content, "缺少 Dashboard 页面路由"
        assert "AdminDashboardHandler" in content, "缺少 AdminDashboardHandler 导入"
        assert "/admin/api/dashboard" in content, "缺少 Dashboard API 路由"

    def test_menu_item_registered(self):
        """db.py 包含数智大屏菜单项"""
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "models", "db.py"
        )
        with open(db_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "数智大屏" in content, "db.py 缺少数智大屏菜单"
        assert "layui-icon-screen-full" in content, "缺少大屏图标"
        assert "/admin/dashboard" in content, "大屏菜单路径未注册"


class TestCSPForDashboard:
    """验证 CSP 支持大屏资源"""

    SETTINGS_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app", "config", "settings.py"
    )

    def test_csp_allows_jsdelivr_for_dashboard_assets(self):
        """CSP 允许从 jsdelivr 加载 Three.js、ECharts 和地球纹理资源。"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # 检查连接源允许 jsdelivr.net
        assert "jsdelivr.net" in content, "CSP 应允许 jsdelivr.net"
        assert "script-src" in content and "https://cdn.jsdelivr.net" in content
        assert "img-src" in content and "https:" in content


class TestEdgeCases:
    """边缘情况测试"""

    def test_empty_warehouse_handling(self):
        """空数据仓库时大屏不崩溃"""
        # get_keyword_frequency 空数据返回 []
        from app.models.data_warehouse import DataWarehouseRepository

        # 无论数据仓库是否有数据，这些方法都不应抛出异常
        try:
            kw = DataWarehouseRepository.get_keyword_frequency(10)
            assert isinstance(kw, list), "返回值应为 list"
        except Exception as e:
            pytest.fail(f"get_keyword_frequency 异常: {e}")

        try:
            stats = DataWarehouseRepository.get_dashboard_stats()
            assert isinstance(stats, dict)
        except Exception as e:
            pytest.fail(f"get_dashboard_stats 异常: {e}")

    def test_trend_data_default_days(self):
        """趋势数据默认返回14天"""
        from app.models.data_warehouse import DataWarehouseRepository
        trend = DataWarehouseRepository.get_trend_data()
        assert len(trend["dates"]) == 14, "默认应为14天趋势数据"
