"""test_sanitize_limit.py — 验证 _sanitize_limit 参数清理函数的边界情况"""
import pytest
from app.models.data_warehouse import _sanitize_limit


class TestSanitizeLimit:
    """_sanitize_limit 单元测试"""

    def test_none_returns_default(self):
        assert _sanitize_limit(None) == 10

    def test_none_custom_default(self):
        assert _sanitize_limit(None, default=50) == 50

    def test_zero_returns_default(self):
        assert _sanitize_limit(0) == 10

    def test_negative_returns_default(self):
        assert _sanitize_limit(-5) == 10
        assert _sanitize_limit(-1) == 10
        assert _sanitize_limit(-100) == 10

    def test_valid_integer_passes_through(self):
        assert _sanitize_limit(1) == 1
        assert _sanitize_limit(5) == 5
        assert _sanitize_limit(10) == 10
        assert _sanitize_limit(100) == 100

    def test_int_string_works(self):
        assert _sanitize_limit("10") == 10
        assert _sanitize_limit("5") == 5
        assert _sanitize_limit("  20  ") == 20

    def test_empty_string_returns_default(self):
        assert _sanitize_limit("") == 10

    def test_non_numeric_string_returns_default(self):
        assert _sanitize_limit("abc") == 10
        assert _sanitize_limit("limit") == 10

    def test_boolean_handling(self):
        assert _sanitize_limit(True) == 1    # int(True) = 1，有效值
        assert _sanitize_limit(False) == 10  # int(False) = 0 → ≤ 0 → 默认值

    def test_float_handling(self):
        assert _sanitize_limit(5.0) == 5
        assert _sanitize_limit(5.7) == 5     # int() 截断
        assert _sanitize_limit(0.5) == 10    # int(0.5) = 0 → 默认值

    def test_float_inf_handled(self):
        """float('inf') 应被 OverflowError 捕获，返回默认值"""
        assert _sanitize_limit(float('inf')) == 10
        assert _sanitize_limit(float('-inf')) == 10

    def test_float_nan_handled(self):
        """float('nan') 应被 ValueError 捕获，返回默认值"""
        assert _sanitize_limit(float('nan')) == 10

    def test_exceeds_hard_limit_capped(self):
        assert _sanitize_limit(1001) == 1000
        assert _sanitize_limit(9999) == 1000
        assert _sanitize_limit(1000) == 1000

    def test_get_recent_with_none_limit(self):
        """集成测试：get_recent(limit=None) 不应抛出异常"""
        from app.models.data_warehouse import DataWarehouseRepository
        items = DataWarehouseRepository.get_recent(limit=None)
        assert isinstance(items, list)

    def test_search_with_none_limit(self):
        """集成测试：search(limit=None) 不应抛出异常"""
        from app.models.data_warehouse import DataWarehouseRepository
        items = DataWarehouseRepository.search(keyword="测试", limit=None)
        assert isinstance(items, list)

    def test_search_with_empty_keyword(self):
        """集成测试：空关键词直接返回 []"""
        from app.models.data_warehouse import DataWarehouseRepository
        items = DataWarehouseRepository.search(keyword="", limit=None)
        assert items == []

    def test_fulltext_search_with_none_limit(self):
        """集成测试：_search_warehouse_fulltext(limit=None) 不应抛出异常"""
        from app.mcp.builtin_tools.warehouse_tools import _search_warehouse_fulltext
        result = _search_warehouse_fulltext(query="测试", limit=None)
        assert isinstance(result, dict)
        assert "total" in result
