import unittest


class TestScriptEngine(unittest.TestCase):
    """测试脚本沙箱引擎。"""

    def test_validate_safe_script(self):
        """安全的脚本应通过验证。"""
        from app.services.script_engine import validate_script
        script = "def transform(data_sources):\n    return str(len(data_sources))"
        is_valid, err = validate_script(script)
        self.assertTrue(is_valid, f"应通过但被拒绝: {err}")

    def test_reject_import(self):
        """含 import 的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "import os\ndef transform(data_sources):\n    return os.getcwd()"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)
        self.assertIn("import", err.lower())

    def test_reject_import_from(self):
        """含 from...import 的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "from os import getcwd\ndef transform(d):\n    return getcwd()"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_reject_exec(self):
        """含 exec() 的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    exec('1+1')\n    return ''"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_reject_eval(self):
        """含 eval() 的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    return eval('1+1')"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_reject_while(self):
        """含 while 循环的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    while True:\n        pass\n    return ''"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_reject_missing_transform(self):
        """缺少 transform 函数的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "x = 1 + 2"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)
        self.assertIn("transform", err.lower())

    def test_reject_open(self):
        """含 open() 的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    open('/etc/passwd')\n    return ''"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_execute_simple_transform(self):
        """简单转换脚本应正确执行。"""
        from app.services.script_engine import execute_transform_script
        script = "def transform(data_sources):\n    return f'共{len(data_sources)}条'"
        result = execute_transform_script(script, [{"a": 1}, {"b": 2}])
        self.assertEqual(result, "共2条")

    def test_execute_with_json(self):
        """使用 json 模块的脚本应正确执行。"""
        from app.services.script_engine import execute_transform_script
        script = "def transform(d):\n    return json.dumps(d)"
        result = execute_transform_script(script, [{"x": 1}])
        self.assertIn('"x"', result)
        self.assertIn("1", result)

    def test_runtime_error_caught(self):
        """脚本运行时异常应被捕获并返回错误信息。"""
        from app.services.script_engine import execute_transform_script
        script = "def transform(d):\n    return d[999]"
        result = execute_transform_script(script, [])
        self.assertTrue(result.startswith("["))

    def test_syntax_error_rejected(self):
        """语法错误的脚本应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d) return d"  # 缺少冒号
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_reject_open_via_getattr(self):
        """通过 getattr 绕过也应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    return getattr(d, 'key')"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_reject_setattr(self):
        """setattr 应被拒绝。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    setattr(d, 'x', 1)\n    return ''"
        is_valid, err = validate_script(script)
        self.assertFalse(is_valid)

    def test_normal_for_loop_allowed(self):
        """正常 for 循环应被允许。"""
        from app.services.script_engine import validate_script
        script = "def transform(d):\n    result = []\n    for item in d:\n        result.append(str(item))\n    return ','.join(result)"
        is_valid, err = validate_script(script)
        self.assertTrue(is_valid, f"for 循环应被允许: {err}")


if __name__ == "__main__":
    unittest.main()
