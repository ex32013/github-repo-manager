# -*- coding: utf-8 -*-
"""冒烟测试: 启动 server 验证关键接口与安全防护。
运行: python tests/smoke.py
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

# CI Windows 控制台默认 cp1252, 中文 print 会崩 → 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PORT = 18995


def start_server():
    import server
    try:
        srv = server.ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    except OSError as e:
        print("FATAL: cannot bind port %d: %s" % (PORT, e))
        print("Processes listening on %d:" % PORT)
        if os.name == "nt":
            os.system('netstat -ano | findstr ":%d"' % PORT)
        sys.exit(3)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def http(path, method="GET", body=None, headers=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), method=method,
                                 data=body.encode() if body else None,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        # Windows CI 网络栈差异: 连接重置/超时也会冒泡, 此处归一化
        return -1, ("EXC:%s:%s" % (type(e).__name__, e)).encode()


def main():
    srv = start_server()
    try:
        time.sleep(1.0)
        fails = []

        # 1. 主页 200 且含 html
        st, body = http("/")
        if st != 200 or b"<html" not in body.lower():
            fails.append("home 200 failed: %d" % st)

        # 2. 设置接口返回合法结构
        st, body = http("/api/settings")
        if st != 200:
            fails.append("/api/settings status %d" % st)
        else:
            d = json.loads(body)
            if not isinstance(d.get("credentials"), list):
                fails.append("settings.credentials not list")

        # 3. 仓库扫描接口(未配置根目录时至少 200 且 repos 是列表)
        st, body = http("/api/repos")
        if st != 200:
            fails.append("/api/repos status %d" % st)
        else:
            d = json.loads(body)
            if not isinstance(d.get("repos"), list):
                fails.append("repos not list")

        # 4. CSRF: 恶意 Origin(127.0.0.1.evil.com)写操作被拒
        st, body = http("/api/settings", method="POST",
                        body=json.dumps({"language": "zh"}),
                        headers={"Content-Type": "application/json",
                                 "Origin": "http://127.0.0.1.evil.com"})
        if st != 403:
            fails.append("evil origin expected 403, got %d" % st)

        # 5. 正常本机 Origin 放行
        st, body = http("/api/settings", method="POST",
                        body=json.dumps({"language": "zh"}),
                        headers={"Content-Type": "application/json",
                                 "Origin": "http://127.0.0.1:%d" % PORT})
        if st != 200:
            fails.append("local origin expected 200, got %d" % st)

        # 6. 超大 body 被拒(413 或连接被拒皆视为防护生效; Windows 网络栈差异)
        st, _ = http("/api/settings", method="POST", body="x" * (2 * 1024 * 1024),
                     headers={"Content-Type": "application/json"})
        if st not in (413, -1):   # -1 = 连接重置/异常, 同样表示被拒
            fails.append("huge body expected 413/reject, got %d" % st)

        # 7. 非法 JSON 容错(不 500)
        st, _ = http("/api/settings", method="POST", body="not-json",
                     headers={"Content-Type": "application/json"})
        if st != 200:
            fails.append("bad json expected 200, got %d" % st)

        # 8. token 校验: 无 token 的写操作... 本机模式无 token 也放行(设计如此), 只验证不 500
        st, _ = http("/api/release", method="POST", body=json.dumps({"path": "/nonexist", "version": "v9.9.9"}),
                     headers={"Content-Type": "application/json"})
        if st != 200:  # 批量发版接口对不存在仓库返回 200 + ok:False
            fails.append("missing repo release expected 200(ok:false), got %d" % st)

        # 9. 批量发版: 空列表应 400
        st, _ = http("/api/release", method="POST", body=json.dumps({"paths": [], "version": "v9.9.9"}),
                     headers={"Content-Type": "application/json"})
        if st != 400:
            fails.append("empty paths release expected 400, got %d" % st)

        # 10. 云端仓库接口: 无凭据时返回结构合法
        st, body = http("/api/cloud-repos")
        if st != 200:
            fails.append("/api/cloud-repos status %d" % st)
        else:
            d = json.loads(body)
            if not isinstance(d.get("repos"), list):
                fails.append("cloud-repos.repos not list")
            if "has_credentials" not in d:
                fails.append("cloud-repos missing has_credentials")

        # 11. 克隆接口: 非法 url 不 500
        st, _ = http("/api/clone", method="POST", body=json.dumps({"url": "", "dir": ""}),
                     headers={"Content-Type": "application/json"})
        if st != 400:
            fails.append("empty url clone expected 400, got %d" % st)

        # 12. config 接口返回 home_dir
        st, body = http("/api/config")
        if st != 200:
            fails.append("/api/config status %d" % st)
        else:
            d = json.loads(body)
            if not d.get("home_dir"):
                fails.append("config missing home_dir")

        if fails:
            print("SMOKE FAILED:")
            for f in fails:
                print("  -", f)
            sys.exit(1)
        print("SMOKE OK: home/API/CSRF/body-limit/batch/cloud/clone all passed")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    import sys as _s
    print("PY=%s OS=%s CWD=%s" % (_s.version.split()[0], os.name, os.getcwd()))
    main()
