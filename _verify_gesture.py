"""快速验证手势修改的配置正确性"""
import sys, os
os.chdir(r'D:\.a\BLISTH\finderos')
sys.path.insert(0, '.')

from app.config.settings import settings

print('VERSION:', settings.VERSION)

csp = settings.SECURITY_HEADERS.get('Content-Security-Policy', '')
assert "'wasm-unsafe-eval'" in csp, "CSP missing wasm-unsafe-eval"
assert "worker-src" in csp and "blob:" in csp, "CSP missing worker-src blob:"
assert "connect-src" in csp and "blob:" in csp, "CSP missing connect-src blob:"
print("[PASS] CSP 配置正确")

pp = settings.SECURITY_HEADERS.get('Permissions-Policy', '')
assert "camera=(self)" in pp, "Permissions-Policy missing camera=(self)"
assert "camera=()" not in pp, "camera should not be fully disabled"
print("[PASS] Permissions-Policy 配置正确")

# 验证模板文件和手势JS存在
tpl = r'app/templates/user_chat.html'
js = r'app/static/js/gesture.js'
test_file = r'test/test_gesture_issue15.py'
for f in [tpl, js, test_file]:
    assert os.path.exists(f), f"{f} 不存在"
print(f"[PASS] 关键文件存在")

# 验证模板包含手势元素
with open(tpl, 'r', encoding='utf-8') as f:
    content = f.read()
assert 'gesture-container' in content
assert 'gesture-video' in content
assert 'btn-camera' in content
assert 'toggleCamera' in content
assert 'handleGesture' in content
assert 'sendGestureMessage' in content
assert '@天气' in content
assert '@随机音乐' in content
assert '@新闻聚合' in content
assert 'beforeunload' in content
# 验证非空消息（修复关键Bug #1）
assert '查看当前天气' in content
assert '推荐一首歌' in content
assert '获取最新新闻' in content
print("[PASS] user_chat.html 手势集成完整")

# 验证gesture.js
with open(js, 'r', encoding='utf-8') as f:
    js_content = f.read()
assert 'GestureDetector' in js_content
assert 'GESTURE_MESSAGE_MAP' in js_content
assert 'locateFile' in js_content
assert '_classifyGesture' in js_content
assert '_isFingerExtended' in js_content
assert '_clearCanvas' in js_content
assert 'destroy' in js_content
assert 'VICTORY' in js_content and 'FIST' in js_content and 'PALM' in js_content
print("[PASS] gesture.js 结构正确")

print("\n=== 全部验证通过 ===")
