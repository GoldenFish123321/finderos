from pathlib import Path
import re
import shutil
import subprocess

import pytest


ACCOUNT_TEMPLATE = Path("app/templates/user_account.html")


def _account_template() -> str:
    return ACCOUNT_TEMPLATE.read_text(encoding="utf-8")


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


def test_user_account_inline_javascript_has_valid_syntax(tmp_path):
    """账户页人脸交互脚本必须保持可解析。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for JavaScript syntax validation")

    scripts = re.findall(r"<script(?:[^>]*)>(.*?)</script>", _account_template(), flags=re.S)
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
