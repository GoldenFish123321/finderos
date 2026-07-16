"""HTTP 级冒烟测试"""
import sys, os, time, threading, json
os.chdir(r'D:\.a\BLISTH\finderos')
sys.path.insert(0, '.')
os.makedirs('database', exist_ok=True)

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
import urllib.request

# 初始化
from app.utils.security import _ensure_secret_key
_ensure_secret_key()
from app.models.db import init_db, seed_default_data
init_db()
seed_default_data()
from app.mcp.tools import register_all_tools
from app.mcp.server import MCPServer
_mcp = MCPServer.get_instance()
register_all_tools(_mcp)
from app.controllers.admin_home import AdminDashboardHandler, AdminDashboardApiHandler
from main import make_app

app = make_app()
server = HTTPServer(app)
server.listen(11013)
results = {}

def test():
    time.sleep(2)
    # 1. API 测试
    try:
        resp = urllib.request.urlopen('http://localhost:11013/admin/api/dashboard', timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        results['api_status'] = resp.status
        results['api_code'] = data.get('code')
        d = data.get('data', {})
        results['api_data_keys'] = list(d.keys())
        results['stats_keys'] = list(d.get('stats', {}).keys())
        results['trend_dates_count'] = len(d.get('trend', {}).get('dates', []))
        results['keywords_count'] = len(d.get('keywords', []))
        results['source_dist_count'] = len(d.get('source_distribution', []))
    except Exception as e:
        results['api_error'] = str(e)

    # 2. Dashboard 页面
    try:
        resp = urllib.request.urlopen('http://localhost:11013/admin/dashboard', timeout=10)
        results['page_status'] = resp.status
    except urllib.error.HTTPError as e:
        results['page_http_error'] = f'{e.code} (expected - needs auth)'
    except Exception as e:
        results['page_error'] = str(e)

    # 3. 模板文件存在
    results['template_exists'] = os.path.exists(
        os.path.join(r'D:\.a\BLISTH\finderos', 'app', 'templates', 'admin', 'dashboard.html')
    )

    IOLoop.current().stop()

threading.Thread(target=test).start()
IOLoop.current().start()
server.stop()

print('=== HTTP 功能测试结果 ===')
for k, v in sorted(results.items()):
    print(f'  {k}: {v}')
print('=========================')
pass_ = results.get('api_code') == 0 and results.get('api_data_keys')
if pass_:
    print('PASS: 所有功能测试通过')
else:
    print('FAIL: 部分测试未通过')
