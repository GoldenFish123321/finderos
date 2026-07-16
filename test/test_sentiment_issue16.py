"""
Issue #16 — 舆情大屏（敏感词预警+AI风析）

验证内容：
1. 敏感词模型表创建和种子数据
2. 扫描逻辑代码存在且可调用
3. Handler 存在且可导入
4. 模板包含所需元素
5. 路由和菜单项已注册
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSensitiveWordModel:
    """验证敏感词模型"""

    def test_module_importable(self):
        from app.models.sensitive_word import SensitiveWordRepository
        assert SensitiveWordRepository is not None

    def test_table_init(self):
        from app.models.sensitive_word import SensitiveWordRepository
        SensitiveWordRepository.init_table()

    def test_seed_data(self):
        from app.models.sensitive_word import SensitiveWordRepository
        SensitiveWordRepository.seed_default()

    def test_get_all_enabled(self):
        from app.models.sensitive_word import SensitiveWordRepository
        words = SensitiveWordRepository.get_all_enabled()
        assert isinstance(words, list)

    def test_get_alert_stats(self):
        from app.models.sensitive_word import SensitiveWordRepository
        stats = SensitiveWordRepository.get_alert_stats()
        for k in ("total", "pending", "high_severity", "trend", "sources"):
            assert k in stats, f"缺少统计字段 {k}"

    def test_scan_all_returns_dict(self):
        from app.models.sensitive_word import SensitiveWordRepository
        result = SensitiveWordRepository.scan_all()
        assert isinstance(result, dict)
        assert "total" in result
        assert "warehouse" in result
        assert "conversation" in result

    def test_recent_alerts(self):
        from app.models.sensitive_word import SensitiveWordRepository
        alerts = SensitiveWordRepository.get_recent_alerts(5)
        assert isinstance(alerts, list)

    def test_methods_exist(self):
        from app.models.sensitive_word import SensitiveWordRepository
        methods = [
            "init_table", "seed_default", "get_all_enabled",
            "scan_warehouse", "scan_conversations", "scan_all",
            "get_alerts", "get_recent_alerts", "get_alert_stats",
            "update_alert_status", "get_alert_detail",
            "add", "delete",
            "analyze_alert_with_ai", "_local_analyze",
            "analyze_pending_alerts", "scan_and_analyze_all",
        ]
        for m in methods:
            assert hasattr(SensitiveWordRepository, m), f"缺少方法 {m}"


class TestSentimentHandler:
    """验证 Handler"""

    def test_handler_importable(self):
        from app.controllers.admin_sentiment import (
            AdminSentimentHandler, AdminSentimentApiHandler,
            AdminSentimentScanHandler, AdminSentimentAlertDetailHandler,
            AdminSentimentResolveHandler,
        )
        assert AdminSentimentHandler is not None
        assert AdminSentimentApiHandler is not None
        assert AdminSentimentScanHandler is not None

    def test_handler_inherits_admin_base(self):
        from app.controllers.admin_sentiment import AdminSentimentHandler
        from app.controllers.admin_base import AdminBaseHandler
        assert issubclass(AdminSentimentHandler, AdminBaseHandler)


class TestSentimentTemplate:
    """验证模板"""

    TEMPLATE_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app", "templates", "admin", "sentiment.html"
    )

    def test_template_exists(self):
        assert os.path.exists(self.TEMPLATE_PATH)

    def test_required_elements(self):
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            c = f.read()
        elements = [
            "sentiment-wrap", "sent-header",
            "chart-trend", "chart-source", "chart-severity",
            "alert-scroll", "alert-item",
            "triggerScan", "refreshSentiment",
            "initCharts", "disposeChart",
            "echarts", "sent-panel",
            "word-tags", "word-tag",
        ]
        for el in elements:
            assert el in c, f"模板缺少元素: {el}"

    def test_stats_cards(self):
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            c = f.read()
        assert "stat-total" in c
        assert "stat-pending" in c
        assert "stat-high" in c


class TestAIAnalysis:
    """验证 AI 语义分析功能"""

    def test_local_analyze_returns_dict(self):
        from app.models.sensitive_word import SensitiveWordRepository
        result = SensitiveWordRepository._local_analyze(
            "测试银行卡密码转账内容", "诈骗", "warehouse"
        )
        import json
        parsed = json.loads(result)
        assert "risk_level" in parsed
        assert "analysis" in parsed
        assert "suggestion" in parsed

    def test_scan_and_analyze(self):
        from app.models.sensitive_word import SensitiveWordRepository
        result = SensitiveWordRepository.scan_and_analyze_all()
        assert "scan" in result
        assert "analysis_count" in result

    def test_analyze_pending(self):
        from app.models.sensitive_word import SensitiveWordRepository
        results = SensitiveWordRepository.analyze_pending_alerts(limit=5)
        assert isinstance(results, list)


class TestRoutesAndMenu:
    """验证路由和菜单"""

    def test_routes_registered(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py"),
                  "r", encoding="utf-8") as f:
            c = f.read()
        assert "/admin/sentiment" in c
        assert "AdminSentimentHandler" in c
        assert "SentimentScanner" in c

    def test_menu_item(self):
        with open(os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "app", "models", "db.py"), "r", encoding="utf-8") as f:
            c = f.read()
        assert "舆情大屏" in c
        assert "layui-icon-log" in c
        assert "/admin/sentiment" in c


class TestScheduler:
    """验证调度器"""

    def test_scanner_class_exists(self):
        from app.services.scheduler import SentimentScanner
        assert SentimentScanner is not None
        assert hasattr(SentimentScanner, "start")
        assert hasattr(SentimentScanner, "stop")


class TestPermissions:
    """验证权限配置"""

    def test_permission_aliases(self):
        with open(os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "app", "controllers", "admin_base.py"),
                "r", encoding="utf-8") as f:
            c = f.read()
        assert "/admin/api/sentiment" in c
        assert "/admin/api/sentiment/scan" in c
        assert "/admin/api/sentiment/detail" in c
