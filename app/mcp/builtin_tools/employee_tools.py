"""
employee_tools.py — 数字员工类 MCP 工具处理函数

工具:
- list_digital_employees: 员工列表
- invoke_digital_employee: 调用指定员工 (v0.10 新增)
"""

from typing import Any, Dict


def _list_digital_employees() -> Dict[str, Any]:
    """列出所有启用的数字员工。"""
    from app.models.digital_employee import DigitalEmployeeRepository
    employees = DigitalEmployeeRepository.get_enabled()
    return {
        "total": len(employees),
        "employees": [
            {
                "id": e["id"],
                "name": e["name"],
                "type": e.get("employee_type", "llm"),
                "description": e.get("description", ""),
            }
            for e in employees
        ],
    }


async def _invoke_digital_employee(employee_name: str, message: str) -> Dict[str, Any]:
    """调用指定数字员工执行任务（v0.10 新增）。

    支持按名称精确匹配或 ID 查找员工。
    """
    from app.models.digital_employee import DigitalEmployeeRepository

    # 按名称查找
    emp = None
    try:
        emp_id = int(employee_name)
        emp = DigitalEmployeeRepository.get_by_id(emp_id)
    except ValueError:
        # 按名称精确匹配
        employees, _ = DigitalEmployeeRepository.get_all(page=1, page_size=200)
        for e in employees:
            if e["name"] == employee_name:
                emp = e
                break
        # 如果没有精确匹配，不做模糊匹配（安全性考虑）

    if not emp:
        return {
            "success": False,
            "error": f"数字员工「{employee_name}」不存在",
            "hint": "使用 list_digital_employees 查看可用员工列表",
        }

    emp_type = emp.get("employee_type", "llm")

    if emp_type == "api":
        # API 型：直接 HTTP 调用
        import urllib.request
        from app.utils.security import validate_url_safe
        api_url = emp.get("api_url", "")
        api_method = emp.get("api_method", "GET")
        api_headers_str = emp.get("api_headers", "{}")
        try:
            import json as _json
            api_headers = _json.loads(api_headers_str)
        except Exception:
            api_headers = {}

        # 替换 URL 中的 {message} 占位符
        import urllib.parse
        final_url = api_url.replace("{message}", urllib.parse.quote(message))

        # SSRF 防护：验证目标 URL 安全性
        if not validate_url_safe(final_url):
            return {
                "success": False,
                "error": "目标 URL 不安全，已阻止请求",
            }

        try:
            req = urllib.request.Request(final_url, headers=api_headers, method=api_method)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "success": True,
                    "employee": emp["name"],
                    "type": "api",
                    "data": body[:5000],
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"API 调用失败: {str(e)}",
            }
    else:
        # LLM 型：返回提示信息，由上层处理
        return {
            "success": True,
            "employee": emp["name"],
            "type": "llm",
            "system_prompt": emp.get("system_prompt", ""),
            "message": message,
            "note": "LLM 型员工需要通过对话系统调用，此处仅返回元信息",
        }
