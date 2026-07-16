"""启动服务器进行快速冒烟测试"""
import sys, os, time, threading, urllib.request

os.chdir(r'D:\.a\BLISTH\finderos')
sys.path.insert(0, '.')

# 创建数据库目录
os.makedirs('database', exist_ok=True)

# 导入并启动
import main
import app

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

# 从 main.py 获取 app
app = main.application  # 假设 main.py 中有 application 变量

print("Server starting on port 11010...")
server = HTTPServer(app)
server.listen(11010)

def test_request():
    time.sleep(2)
    try:
        resp = urllib.request.urlopen('http://localhost:11010/', timeout=5)
        print(f'GET / -> {resp.status}')
        body = resp.read().decode('utf-8', errors='replace')[:200]
        print(f'Body preview: {body}')
    except Exception as e:
        print(f'Request failed: {e}')
    finally:
        IOLoop.current().stop()

threading.Thread(target=test_request).start()
IOLoop.current().start()
server.stop()
print("Server test complete")
