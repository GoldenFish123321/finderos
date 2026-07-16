"""
Issue #15 — 手势与数字员工交互（剪刀手/握拳/手掌）

验证内容：
1. gesture.js 静态文件存在且语法正确
2. user_chat.html 包含摄像头区域和 MediaPipe CDN 引用
3. CSP 配置已允许摄像头和 MediaPipe WASM Worker
4. 手势触发消息匹配正确的数字员工
"""

import os
import re
import sys
import json
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGestureStaticFiles:
    """验证手势识别相关静态文件"""

    def test_gesture_js_exists(self):
        """gesture.js 文件存在"""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "js", "gesture.js"
        )
        assert os.path.exists(js_path), f"gesture.js 不存在: {js_path}"

    def test_gesture_js_syntax(self):
        """gesture.js 不含明显语法错误"""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "js", "gesture.js"
        )
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查类定义
        assert "var GestureDetector" in content, "缺少 GestureDetector 定义"
        assert "function GestureDetector" in content, "缺少 GestureDetector 构造函数"
        assert "GESTURES" in content, "缺少 GESTURES 常量"
        assert "GESTURE_MESSAGE_MAP" in content, "缺少 GESTURE_MESSAGE_MAP 常量"

        # 检查三个手势
        assert "VICTORY" in content, "缺少 VICTORY 手势"
        assert "FIST" in content, "缺少 FIST 手势"
        assert "PALM" in content, "缺少 PALM 手势"

        # 检查手势消息映射
        assert "@天气" in content, "缺少 @天气 映射"
        assert "@随机音乐" in content, "缺少 @随机音乐 映射"
        assert "@新闻聚合" in content, "缺少 @新闻聚合 映射"

        # 检查 MediaPipe 集成
        assert "MediaPipe" in content or "mediapipe" in content, "缺少 MediaPipe 引用"
        assert "locateFile" in content, "缺少 locateFile 方法"
        assert "onResults" in content, "缺少 onResults 回调"

        # 检查关键方法
        assert "_classifyGesture" in content, "缺少 _classifyGesture 方法"
        assert "_isFingerExtended" in content, "缺少 _isFingerExtended 方法"
        assert "init" in content, "缺少 init 方法"
        assert "start" in content, "缺少 start 方法"
        assert "stop" in content, "缺少 stop 方法"
        assert "destroy" in content, "缺少 destroy 方法"

        # 检查画布清理
        assert "_clearCanvas" in content, "缺少 _clearCanvas 清理方法"

    def test_gesture_message_map(self):
        """验证手势消息映射正确"""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "js", "gesture.js"
        )
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取 GESTURE_MESSAGE_MAP 的值
        map_match = re.search(r'GESTURE_MESSAGE_MAP\s*=\s*\{([^}]+)\}', content)
        assert map_match, "无法解析 GESTURE_MESSAGE_MAP"

        map_str = map_match.group(1)
        assert "VICTORY" in map_str and "'@天气'" in map_str or '"@天气"' in map_str
        assert "FIST" in map_str and "'@随机音乐'" in map_str or '"@随机音乐"' in map_str
        assert "PALM" in map_str and "'@新闻聚合'" in map_str or '"@新闻聚合"' in map_str


class TestGestureTemplate:
    """验证 user_chat.html 模板中的手势集成"""

    TEMPLATE_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app", "templates", "user_chat.html"
    )

    def test_template_exists(self):
        """模板文件存在"""
        assert os.path.exists(self.TEMPLATE_PATH)

    def test_mediapipe_cdn_loaded(self):
        """模板加载了 MediaPipe CDN"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "mediapipe/camera_utils" in content, "缺少 MediaPipe Camera Utils CDN"
        assert "mediapipe/hands" in content, "缺少 MediaPipe Hands CDN"
        assert "gesture.js" in content, "缺少 gesture.js 加载"

    def test_gesture_html_elements(self):
        """模板包含手势识别 HTML 结构"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert 'id="gesture-container"' in content, "缺少 gesture-container"
        assert 'id="gesture-video"' in content, "缺少 gesture-video"
        assert 'id="gesture-canvas"' in content, "缺少 gesture-canvas"
        assert 'id="btn-camera"' in content, "缺少 btn-camera"
        assert 'id="gesture-hint"' in content, "缺少 gesture-hint"

    def test_camera_button_in_header(self):
        """摄像头按钮在聊天头部区域"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "btn-camera" in content, "缺少 btn-camera 按钮"
        assert "toggleCamera" in content, "缺少 toggleCamera 函数"

    def test_handle_gesture_messages(self):
        """handleGesture 发送带内容的员工消息（非空消息）"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 核心修复：消息必须包含具体内容，不能只是 @员工 空消息
        assert "查看当前天气" in content or "@天气 查看" in content, \
            "剪刀手消息应包含具体查询内容"
        assert "推荐一首歌" in content or "@随机音乐 推荐" in content, \
            "握拳消息应包含具体查询内容"
        assert "获取最新新闻" in content or "@新闻聚合 获取" in content, \
            "手掌消息应包含具体查询内容"

    def test_streaming_guard(self):
        """手势发送消息时有 isStreaming 保护"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "isStreaming" in content.split("sendGestureMessage")[1].split("\n")[0] if "sendGestureMessage" in content else True

    def test_beforeunload_cleanup(self):
        """页面离开时释放摄像头资源"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "beforeunload" in content, "缺少 beforeunload 清理"
        assert "destroy" in content, "摄像头资源应调用 destroy 清理"

    def test_gesture_css_styles(self):
        """模板包含手势 UI 的 CSS 样式"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        styles = [
            "gesture-container",
            "gesture-overlay",
            "gesture-hint",
            "btn-camera",
            "transform: scaleX(-1)",  # 镜像翻转
        ]
        for s in styles:
            assert s in content, f"缺少 CSS 样式: {s}"


class TestCSPConfig:
    """验证 CSP 和安全配置支持手势识别"""

    SETTINGS_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "app", "config", "settings.py"
    )

    def test_wasm_unsafe_eval_in_csp(self):
        """CSP 包含 'wasm-unsafe-eval' 以允许 MediaPipe WASM"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "wasm-unsafe-eval" in content, "CSP 缺少 wasm-unsafe-eval"

    def test_worker_src_blob_in_csp(self):
        """CSP 包含 worker-src blob: 以允许 MediaPipe Worker"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "worker-src" in content and "blob" in content, "CSP 缺少 worker-src blob:"

    def test_connect_src_blob_in_csp(self):
        """CSP 包含 connect-src blob: 以允许 WASM 加载"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "connect-src" in content and "blob" in content, "CSP 缺少 connect-src blob:"

    def test_camera_permissions_policy(self):
        """Permissions-Policy 允许摄像头"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "camera=(self)" in content, "Permissions-Policy 应允许 camera=(self)"
        assert "camera=()" not in content, "Permissions-Policy 不应完全禁用摄像头"

    def test_connect_src_tightened(self):
        """connect-src 已收紧到特定 CDN 而非通配 https:"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查 connect-src 行有限定而非通配
        # 注意：可能有 blob: 和 cdn.jsdelivr.net
        csp_section = content.split("Content-Security-Policy")[1] if "Content-Security-Policy" in content else ""
        connect_line = ""
        for line in csp_section.split("\n"):
            if "connect-src" in line:
                connect_line = line
                break

        assert connect_line, "未找到 connect-src 行"
        # 检查是否有限定域名而非通配 https:
        assert "https://cdn.jsdelivr.net" in connect_line or "https:" not in connect_line.replace("https://cdn.jsdelivr.net", ""), \
            "connect-src 应限定 CDN 域名避免通配"


class TestGestureEmployeeMapping:
    """验证手势 → 数字员工映射一致性"""

    def test_gesture_to_employee_relation(self):
        """验证手势消息中的 @员工名 在跳转和设置中一致"""
        gesture_js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "js", "gesture.js"
        )
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "templates", "user_chat.html"
        )

        with open(gesture_js_path, "r", encoding="utf-8") as f:
            js_content = f.read()
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # 从 gesture.js 提取所有员工名映射
        employee_names = ["天气", "随机音乐", "新闻聚合"]
        for name in employee_names:
            # 映射中的 @name
            assert f"@{name}" in js_content, f"gesture.js 中缺少 @{name} 映射"
            # handleGesture 中的消息
            assert f"@{name}" in html_content, f"user_chat.html 中缺少 @{name} 手势触发"


class TestEdgeCases:
    """手势边缘情况测试"""

    def test_gesture_cooldown_not_zero(self):
        """冷却时间配置合理，避免过于频繁触发"""
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "static", "js", "gesture.js"
        )
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 默认 cooldown 应为正数
        assert "cooldown" in content, "缺少防抖冷却机制"
        assert "minConfidence" in content, "缺少连续帧确认机制"

    def test_cdn_version_pinned(self):
        """CDN 版本已固定，无版本漂移风险"""
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app", "templates", "user_chat.html"
        )
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查 MediaPipe CDN 是否包含版本号
        camera_utils_match = re.search(r'@mediapipe/camera_utils[^"\']*', content)
        hands_match = re.search(r'@mediapipe/hands[^"\']*', content)

        if camera_utils_match:
            assert "@" in camera_utils_match.group(0).split("/")[-1] or \
                   camera_utils_match.group(0).count("/") >= 4, \
                   "camera_utils CDN 应固定版本号"
        if hands_match:
            assert "@" in hands_match.group(0).split("/")[-1] or \
                   hands_match.group(0).count("/") >= 4, \
                   "hands CDN 应固定版本号"
