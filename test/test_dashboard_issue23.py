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


class TestDashboardTemplate:
    """验证 Dashboard 模板"""

    TEMPLATE_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app", "templates", "admin", "dashboard.html"
    )

    def test_template_exists(self):
        """dashbaord.html 文件存在"""
        assert os.path.exists(self.TEMPLATE_PATH), "dashboard.html 不存在"

    def test_cdn_echarts_gl_loaded(self):
        """模板加载了 ECharts-GL CDN"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "echarts-gl" in content, "缺少 echarts-gl CDN"
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
        required_keys = ["total", "deep_collected", "today_count", "source_count", "top_source", "top_source_count"]
        for k in required_keys:
            assert k in stats, f"缺少统计字段 {k}"

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

    def test_connect_src_allows_jsdelivr(self):
        """CSP connect-src 允许 jsdelivr.net 加载纹理"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        # 检查连接源允许 jsdelivr.net
        assert "jsdelivr.net" in content, "CSP 应允许 jsdelivr.net"


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
