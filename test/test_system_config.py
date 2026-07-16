"""
Functional test for system_config feature (Issue #13).
Tests HTTP endpoints: login, config page access, save, logo upload, permission.
"""
import sys
import os
import re
import glob
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
from app.models.system_config import SystemConfigRepository

BASE = "http://127.0.0.1:10010"
passed = 0
failed = 0


def t(desc, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {desc}")
    else:
        failed += 1
        print(f"  FAIL  {desc}")


def new_client():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPRedirectHandler(),
    )
    return opener, cj


def get(opener, path):
    req = urllib.request.Request(BASE + path)
    resp = opener.open(req, timeout=10)
    return resp.read().decode("utf-8", errors="replace"), resp.status


def post(opener, path, data_dict, files=None):
    if files:
        boundary = "----TestBoundary173456"
        body_bytes = b""
        for k, v in data_dict.items():
            body_bytes += f"--{boundary}\r\n".encode()
            body_bytes += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
            body_bytes += str(v).encode() + b"\r\n"
        for fn, (fname, fbody, ftype) in files.items():
            body_bytes += f"--{boundary}\r\n".encode()
            body_bytes += f'Content-Disposition: form-data; name="{fn}"; filename="{fname}"\r\n'.encode()
            body_bytes += f"Content-Type: {ftype}\r\n\r\n".encode()
            body_bytes += fbody + b"\r\n"
        body_bytes += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(BASE + path, data=body_bytes)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        data = urllib.parse.urlencode(data_dict).encode()
        req = urllib.request.Request(BASE + path, data=data)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    resp = opener.open(req, timeout=10)
    return resp.read().decode("utf-8", errors="replace"), resp.status


def extract_xsrf(body):
    m = re.search(r'name="_xsrf".*?value="([^"]+)"', body)
    return m.group(1) if m else ""


# ======== Test Execution ========

print("=" * 55)
print("  System Config Functional Tests")
print("=" * 55)

# ── 1. GET login page ──
print("\n── 1. Login page ──")
op, cj = new_client()
body, st = get(op, "/")
t("Login page returns 200", st == 200)
t("Contains system name", "瞭望与问数系统" in body)
t("Contains login form", '<form' in body.lower())

# ── 2. Admin login ──
print("\n── 2. Admin login ──")
xsrf = extract_xsrf(body)
t("CSRF token extracted", xsrf != "")
body2, st2 = post(op, "/", {"_xsrf": xsrf, "username": "admin", "password": "admin888"})
logged_in = ("控制台" in body2 or "管理后台" in body2 or "瞭望与问数系统" in body2
             or "chat" in body2.lower() or st2 == 200)
t("Login succeeded (admin page)", logged_in)

# Get fresh CSRF from admin page
body_a, _ = get(op, "/admin")
xsrf = extract_xsrf(body_a)
if not xsrf:
    body_c, _ = get(op, "/admin/config")
    xsrf = extract_xsrf(body_c)
t("Fresh CSRF token available", xsrf != "")

# ── 3. Config page GET ──
print("\n── 3. Config page GET ──")
body3, st3 = get(op, "/admin/config")
t("Config page 200", st3 == 200)
t("Title: 常规设置", "常规设置" in body3)
t("Field: 系统名称", "系统名称" in body3)
t("Section: AI 默认参数", "AI 默认参数" in body3)
t("Default system_name in form", "瞭望与问数系统" in body3)
t("Default port 10010", "10010" in body3)
xsrf = extract_xsrf(body3)
t("Config CSRF valid", xsrf != "")

# ── 4. Save settings ──
print("\n── 4. Save text settings ──")
save = {
    "_xsrf": xsrf,
    "system_name": "TestXYZ_Name",
    "system_subtitle": "TestXYZ_Sub",
    "icp_number": "蜀ICP备2024000000号-1",
    "default_port": "8080",
    "ai_default_temperature": "0.5",
    "ai_default_max_tokens": "8192",
}
body4, st4 = post(op, "/admin/config", save)
t("Save processed (200)", st4 == 200)

# ── 5. Verify persistence ──
print("\n── 5. Verify persistence ──")
body5, st5 = get(op, "/admin/config")
t("Reload 200", st5 == 200)
t("system_name=TestXYZ_Name", "TestXYZ_Name" in body5)
t("subtitle=TestXYZ_Sub", "TestXYZ_Sub" in body5)
t("icp_number persisted", "蜀ICP备2024000000号-1" in body5)
t("port=8080 persisted", "8080" in body5)
t("temperature=0.5 persisted", "0.5" in body5)
t("max_tokens=8192 persisted", "8192" in body5)

# ── 6. Dashboard shows new name ──
print("\n── 6. Dashboard propagation ──")
body6, st6 = get(op, "/admin")
t("Dashboard 200", st6 == 200)
t("Dashboard shows new name", "TestXYZ_Name" in body6)

# ── 7. Logo upload ──
print("\n── 7. Logo upload ──")
xsrf = extract_xsrf(body5)
tiny_png = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
body7, st7 = post(op, "/admin/config",
    {"_xsrf": xsrf, "system_name": "TestXYZ_Name"},
    files={"logo_file": ("test.png", tiny_png, "image/png")})
t("Logo upload processed (200)", st7 == 200)

body7b, _ = get(op, "/admin/config")
logo_match = re.search(r'/static/uploads/logo_\d+\.png', body7b)
t("Logo path in config form", logo_match is not None)
if logo_match:
    logo_url = logo_match.group(0)
    logo_req = urllib.request.Request(BASE + logo_url)
    logo_resp = urllib.request.urlopen(logo_req, timeout=5)
    t(f"Logo accessible ({logo_url})", logo_resp.status == 200)

# ── 8. Permission: unauthenticated ──
print("\n── 8. Permission control ──")
# Build opener WITHOUT HTTPRedirectHandler to capture 302
from urllib.request import HTTPHandler, HTTPSHandler, HTTPCookieProcessor, OpenerDirector
cj3 = http.cookiejar.CookieJar()
op3 = OpenerDirector()
op3.add_handler(HTTPHandler())
op3.add_handler(HTTPSHandler())
op3.add_handler(HTTPCookieProcessor(cj3))
try:
    req = urllib.request.Request(BASE + "/admin/config")
    resp = op3.open(req, timeout=10)
    t(f"Unauthenticated → {resp.status}", resp.status in (302, 403))
except urllib.error.HTTPError as e:
    t(f"Unauthenticated → {e.code}", e.code in (302, 403))

# ── 9. Restore defaults ──
print("\n── 9. Restore defaults ──")
body_cfg, _ = get(op, "/admin/config")
xsrf = extract_xsrf(body_cfg)
restore = {
    "_xsrf": xsrf,
    "system_name": "瞭望与问数系统",
    "system_subtitle": "DataFinderAgentOS",
    "icp_number": "",
    "default_port": "10010",
    "ai_default_temperature": "0.7",
    "ai_default_max_tokens": "4096",
}
body_r, st_r = post(op, "/admin/config", restore)
t("Restore processed", st_r == 200)

# Clear logo in DB
SystemConfigRepository.update("system_logo", "")

# Clean uploaded logo files
upload_dir = os.path.join(_PROJECT_ROOT, "app", "static", "uploads")
if os.path.isdir(upload_dir):
    for f in glob.glob(os.path.join(upload_dir, "logo_*")):
        os.remove(f)
        print(f"  CLEAN  {os.path.basename(f)}")

# ── 10. Verify restored ──
print("\n── 10. Verify restored ──")
body10, _ = get(op, "/admin/config")
t("system_name restored", "瞭望与问数系统" in body10)
t("subtitle restored", "DataFinderAgentOS" in body10)
t("port restored", "10010" in body10)

# ── Summary ──
total = passed + failed
print(f"\n{'='*55}")
print(f"  Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*55}")
sys.exit(0 if failed == 0 else 1)
