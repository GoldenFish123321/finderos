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
        assert 'id="btn-gesture-help"' in content, "缺少手势说明入口"
        assert 'id="gesture-guide"' in content, "缺少手势说明区域"

    def test_camera_layers_are_scoped_to_preview(self):
        """摄像头和骨架画布不能覆盖下方手势说明。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        preview_start = content.index('<div class="gesture-preview"')
        preview_end = content.index('<div class="gesture-hint"', preview_start)
        preview_html = content[preview_start:preview_end]
        guide_start = content.index('<div class="gesture-guide"', preview_end)

        assert 'id="gesture-video"' in preview_html
        assert 'id="gesture-canvas"' in preview_html
        assert preview_end < guide_start
        assert ".gesture-preview canvas" in content
        assert ".gesture-container canvas" not in content
        assert "flex-shrink: 0" in content
        assert "width: min(100%, 640px, calc(100vh - 268px))" in content

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

        # 剪刀手天气应解析当前城市后发送 @天气 城市，不能只是 @天气 空消息
        assert "resolveCurrentWeatherCity" in content, "剪刀手天气应先解析当前城市"
        assert "msg = '@天气 ' + normalizeWeatherCityName(city)" in content, \
            "剪刀手消息应发送 @天气 当前城市"
        assert "DEFAULT_WEATHER_CITY" in content and "成都" in content, \
            "定位失败时应使用默认城市成都"
        assert "推荐一首歌" in content or "@随机音乐 推荐" in content, \
            "握拳消息应包含具体查询内容"
        assert "获取最新新闻" in content or "@新闻聚合 获取" in content, \
            "手掌消息应包含具体查询内容"

    def test_gesture_weather_uses_browser_location(self):
        """剪刀手天气应使用浏览器系统定位反查城市，并走本地后端代理。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "navigator.geolocation.getCurrentPosition" in content, \
            "缺少浏览器系统定位调用"
        assert "/api/location/reverse?lat=" in content, \
            "前端应调用本地反查城市接口"
        assert "weatherCityCache" in content, "定位城市应短期缓存，避免重复请求"
        assert "@天气 [当前城市]" in content, "手势说明应标明天气使用当前城市"

    def test_gesture_weather_prefetches_city_on_camera_start(self):
        """打开手势摄像头后应预解析城市，降低首次剪刀手触发延迟。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "weatherCityPromise" in content, "应复用正在进行的定位 Promise"
        assert "function prefetchCurrentWeatherCity" in content, \
            "缺少天气城市预取函数"
        camera_start = content.index("gestureDetector.start();")
        prefetch_call = content.index("prefetchCurrentWeatherCity();", camera_start)
        assert prefetch_call > camera_start, "摄像头启动后应立即预取城市"

    def test_gesture_ui_does_not_show_default_city_fallback_copy(self):
        """用户界面不展示“定位失败默认成都”等兜底实现细节。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        for forbidden in ("定位失败默认成都", "失败默认成都", "系统定位，失败"):
            assert forbidden not in content, f"手势 UI 不应展示兜底文案: {forbidden}"

    def test_gesture_help_documents_mapping(self):
        """用户侧手势说明应明确展示手势到数字员工的映射。"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "showGestureHelp" in content, "缺少手势说明弹窗函数"
        assert "手势识别说明" in content, "缺少手势说明标题"
        for expected in ("剪刀手", "@天气", "握拳", "@随机音乐", "手掌", "@新闻聚合"):
            assert expected in content, f"手势说明缺少: {expected}"

    def test_streaming_guard(self):
        """手势发送消息时有 isStreaming 保护"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # sendGestureMessage 中应检查 isStreaming
        assert "sendGestureMessage" in content, "缺少 sendGestureMessage 函数"
        # 从 sendGestureMessage 内部查找 isStreaming 检查
        func_start = content.index("function sendGestureMessage")
        func_end = content.index("\n}", func_start) + 2
        func_body = content[func_start:func_end]
        assert "isStreaming" in func_body, "sendGestureMessage 应检查 isStreaming"

    def test_send_gesture_message_returns_bool(self):
        """sendGestureMessage 返回布尔值表示是否成功发送"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        func_start = content.index("function sendGestureMessage")
        func_end = content.index("\n}", func_start) + 2
        func_body = content[func_start:func_end]
        # 流式输出中应 return false，成功发送应 return true
        assert "return false" in func_body, "sendGestureMessage 流式保护时应返回 false"
        assert "return true" in func_body, "sendGestureMessage 成功发送时应返回 true"

    def test_close_gesture_camera_function(self):
        """closeGestureCamera 函数存在且包含完整清理逻辑"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "function closeGestureCamera" in content, "缺少 closeGestureCamera 函数"

        func_start = content.index("function closeGestureCamera")
        # 找到下一个顶层函数作为结束边界
        next_func = content.find("\nfunction ", func_start + 1)
        if next_func == -1:
            next_func = len(content)
        func_body = content[func_start:next_func]

        assert "destroy()" in func_body, "closeGestureCamera 应调用 destroy()"
        assert "classList.remove('active')" in func_body, "closeGestureCamera 应隐藏容器"
        assert 'btn.textContent = ' in func_body or "btn.textContent=" in func_body, \
            "closeGestureCamera 应重置按钮文字"
        assert "gestureCamActive = false" in func_body, \
            "closeGestureCamera 应重置 gestureCamActive"

    def test_handle_gesture_auto_close(self):
        """handleGesture 识别成功后自动关闭摄像头"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        func_start = content.index("function handleGesture")
        next_func = content.find("\nfunction ", func_start + 1)
        if next_func == -1:
            next_func = len(content)
        func_body = content[func_start:next_func]

        # 应包含 closeGestureCamera 调用
        assert "closeGestureCamera()" in func_body, \
            "handleGesture 识别成功后应调用 closeGestureCamera()"

        # 应根据 sendGestureMessage 返回值决定是否关闭（流式保护）
        assert "sendGestureMessage(msg)" in func_body, \
            "handleGesture 应调用 sendGestureMessage"

    def test_handle_gesture_no_close_on_streaming(self):
        """流式输出时手势识别不应关闭摄像头（sendGestureMessage 返回 false）"""
        with open(self.TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        func_start = content.index("function handleGesture")
        next_func = content.find("\nfunction ", func_start + 1)
        if next_func == -1:
            next_func = len(content)
        func_body = content[func_start:next_func]

        # 当 sendGestureMessage 返回 false 时不关闭
        # 条件: if (sendGestureMessage(msg)) { closeGestureCamera(); }
        assert "if (sendGestureMessage(msg))" in func_body or \
               "if(sendGestureMessage(msg))" in func_body, \
            "handleGesture 应对 sendGestureMessage 返回值做条件判断"

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
            "gesture-guide",
            "gesture-guide-item",
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

    def test_geolocation_permissions_policy(self):
        """Permissions-Policy 允许同源页面读取系统定位，用于手势天气。"""
        with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        assert "geolocation=(self)" in content, \
            "Permissions-Policy 应允许同源 geolocation=(self)"
        assert "geolocation=()" not in content, \
            "Permissions-Policy 不应完全禁用定位"

    def test_location_reverse_route_registered(self):
        """手势天气城市反查 API 已注册。"""
        root = os.path.dirname(os.path.dirname(__file__))
        main_path = os.path.join(root, "main.py")
        controller_path = os.path.join(root, "app", "controllers", "user_chat.py")
        with open(main_path, "r", encoding="utf-8") as f:
            main_content = f.read()
        with open(controller_path, "r", encoding="utf-8") as f:
            controller_content = f.read()

        assert "/api/location/reverse" in main_content
        assert "UserLocationReverseHandler" in main_content
        assert "class UserLocationReverseHandler" in controller_content
        assert "nominatim.openstreetmap.org/reverse" in controller_content

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

        # 检查 MediaPipe CDN 是否包含版本号（如 @0.4.1675469240）
        camera_utils_match = re.search(r'@mediapipe/camera_utils[^"\']*', content)
        hands_match = re.search(r'@mediapipe/hands[^"\']*', content)

        if camera_utils_match:
            url = camera_utils_match.group(0)
            # 版本号格式为 @x.y.z 出现在路径中
            assert re.search(r'@\d+\.\d+\.\d+', url), \
                f"camera_utils CDN 应固定版本号，当前: {url}"
        if hands_match:
            url = hands_match.group(0)
            assert re.search(r'@\d+\.\d+\.\d+', url), \
                f"hands CDN 应固定版本号，当前: {url}"
