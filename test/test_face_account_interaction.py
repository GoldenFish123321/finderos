from pathlib import Path
import re
import shutil
import subprocess

import pytest


ACCOUNT_TEMPLATE = Path("app/templates/user_account.html")
LOGIN_TEMPLATE = Path("app/templates/login.html")
AUTH_CONTROLLER = Path("app/controllers/auth.py")


def _account_template() -> str:
    return ACCOUNT_TEMPLATE.read_text(encoding="utf-8")


def _login_template() -> str:
    return LOGIN_TEMPLATE.read_text(encoding="utf-8")


def _auth_controller() -> str:
    return AUTH_CONTROLLER.read_text(encoding="utf-8")


def test_face_registration_requires_user_confirmation_after_capture():
    """账户页人脸注册应先拍照预览，再由用户确认使用后提交。"""
    html = _account_template()

    assert "📸 拍照预览" in html
    assert "✅ 确认使用" in html
    assert "🔄 重新拍照" in html
    assert "facePendingBlob" in html
    assert "function confirmFaceRegistration()" in html
    assert "function retakeFace()" in html

    capture_start = html.index("function captureFace()")
    confirm_start = html.index("function confirmFaceRegistration()")
    capture_body = html[capture_start:confirm_start]
    confirm_body = html[confirm_start:]

    assert "fetch('/account'" not in capture_body, "拍照预览阶段不应直接提交注册"
    assert "facePendingBlob = blob" in capture_body
    assert "face-confirm-actions" in capture_body
    assert "fetch('/account'" in confirm_body, "确认使用后才应提交注册请求"
    assert "formData.append('face_image', facePendingBlob" in confirm_body


def test_face_registration_stops_camera_after_preview_and_before_unload():
    """拍照预览后和离开页面时均应释放摄像头。"""
    html = _account_template()
    assert "function stopFaceCamera()" in html
    assert "stopFaceCamera();" in html
    assert "beforeunload" in html



def test_face_toggle_remains_clickable_before_registration():
    """未注册人脸时开关也应可点击，并引导用户先拍照注册。"""
    html = _account_template()
    match = re.search(r'<input[^>]+id="face-toggle"[^>]*>', html, flags=re.S)
    assert match, "缺少人脸登录开关"
    assert "disabled" not in match.group(0), "未注册时不应禁用开关，避免用户误以为按钮坏了"
    assert "data-face-registered" in match.group(0)
    assert "FACE_REGISTERED" in html
    assert "localStorage" not in html, "人脸登录启用状态不能只保存在浏览器本地"
    assert "openCamera();" in html, "未注册时点击开关应引导打开摄像头注册"
    assert "请先完成拍照注册" in html


def test_face_toggle_requires_server_confirmation_and_persistence():
    """勾选确认应提交后端持久化；登录校验也必须以后端状态为准。"""
    account_html = _account_template()
    login_html = _login_template()
    auth_py = _auth_controller()

    assert "formData.append('action', 'face_toggle')" in account_html
    assert "formData.append('enabled', checked ? '1' : '0')" in account_html
    assert "fetch('/account'" in account_html
    assert "FACE_ENABLED" in account_html
    assert "勾选确认后才能使用人脸登录" in account_html

    assert "face_login_enabled" not in login_html
    assert "localStorage" not in login_html
    assert "UserRepository.is_face_login_enabled(username)" in auth_py
    assert 'get_body_argument("face_login_enabled"' not in auth_py
    assert 'action == "face_toggle"' in auth_py
    assert "set_face_login_enabled" in auth_py
    assert 'error=self.get_query_argument("error", "")' in auth_py


def test_user_account_inline_javascript_has_valid_syntax(tmp_path):
    """账户页人脸交互脚本必须保持可解析。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript syntax validation")

    rendered = _account_template()
    rendered = rendered.replace("{{ 'true' if face_registered else 'false' }}", "false")
    rendered = rendered.replace("{{ 'true' if face_enabled else 'false' }}", "false")
    scripts = re.findall(r"<script(?:[^>]*)>(.*?)</script>", rendered, flags=re.S)
    assert any("function confirmFaceRegistration()" in script for script in scripts)

    for index, script in enumerate(scripts):
        if not script.strip():
            continue
        script_path = tmp_path / f"user_account_inline_{index}.js"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
