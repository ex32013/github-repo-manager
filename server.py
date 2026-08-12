# -*- coding: utf-8 -*-
"""github-repo-manager 后端入口。

- 静态服务(index.html)
- API 路由(/api/*)
- 安全: 仅监听 127.0.0.1(默认)、CSRF Origin 精确匹配、body 1MB 上限、no-store、错误脱敏
"""
import argparse
import json
import os
import re
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import github_api
import i18n
import release
import repo_scanner

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(ROOT, "index.html")
MAX_BODY = 1024 * 1024
SESSION_TOKEN = secrets.token_urlsafe(16)

# 请求超时防护(线程级)
import socket
socket.setdefaulttimeout(30)


class Handler(BaseHTTPRequestHandler):
    server_version = "repo-manager/0.1"
    protocol_version = "HTTP/1.1"

    # ---- 工具 ----
    def _security_headers(self, extra=None):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        for k, v in (extra or {}).items():
            self.send_header(k, v)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._security_headers({"Content-Type": "application/json; charset=utf-8",
                                "Content-Length": str(len(body))})
        self.end_headers()
        self.wfile.write(body)

    def _csrf_ok(self):
        """CSRF/DNS-rebinding 防护: Origin/Referer 精确匹配本机地址。"""
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not origin:
            return True  # 非浏览器请求(命令行), 无 CSRF 风险
        try:
            host = (urllib.parse.urlparse(origin).hostname or "").lower()
        except Exception:
            return False
        if not host:
            return False
        # 精确匹配, 禁止 127.* 前缀通配(防 127.0.0.1.evil.com 绕过)
        return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    def _read_json(self):
        try:
            ln = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            ln = 0
        if ln <= 0:
            return {}
        if ln > MAX_BODY:
            remaining = ln
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            return {"__too_large__": True}
        try:
            return json.loads(self.rfile.read(ln).decode("utf-8", "replace"))
        except Exception:
            return {}

    def _index_html(self):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return f.read()

    # ---- HTTP ----
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            body = self._index_html().encode("utf-8")
            self.send_response(200)
            self._security_headers({"Content-Type": "text/html; charset=utf-8",
                                    "Content-Length": str(len(body))})
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/config":
            self._json({"session_token": SESSION_TOKEN})
            return
        if path == "/api/settings":
            self._json(self._public_settings())
            return
        if path == "/api/repos":
            cfg = config.load()
            self._json({"repos": repo_scanner.discover(cfg)})
            return
        if path == "/api/overview":
            # 仓库 + Actions + Release 汇总(Phase 1 核心)
            self._json(self._overview())
            return
        self.send_error(404)

    def do_POST(self):
        if not self._csrf_ok():
            self._json({"error": "forbidden"}, 403)
            return
        path = urllib.parse.urlparse(self.path).path
        body = self._read_json()
        if isinstance(body, dict) and body.get("__too_large__"):
            self._json({"error": "request too large"}, 413)
            return
        if path == "/api/settings":
            self._save_settings(body)
            return
        if path == "/api/refresh":
            self._json({"ok": True, "repos": repo_scanner.discover(config.load())})
            return
        if path == "/api/release":
            self._do_release(body)
            return
        self.send_error(404)

    # ---- 业务 ----
    def _public_settings(self):
        """对外配置(不返回 token 明文)。"""
        cfg = config.load()
        creds = github_api.discover_credentials(cfg.get("credentials"))
        return {
            "language": cfg.get("language", "auto"),
            "root_dirs": cfg.get("root_dirs", []),
            "manual_repos": cfg.get("manual_repos", []),
            "port": cfg.get("port", 8080),
            "credentials": [{"name": c.get("name"), "api_base": c.get("api_base"),
                             "default": c.get("default", False), "auto": c.get("auto", False),
                             "has_token": bool(c.get("token"))} for c in creds],
        }

    def _save_settings(self, body):
        cfg = config.load()
        if "language" in body:
            lang = body.get("language")
            if lang in ("auto", "zh", "en"):
                cfg["language"] = lang
        if "root_dirs" in body and isinstance(body["root_dirs"], list):
            cfg["root_dirs"] = [x.strip() for x in body["root_dirs"] if isinstance(x, str) and x.strip()]
        if "manual_repos" in body and isinstance(body["manual_repos"], list):
            cfg["manual_repos"] = [x.strip() for x in body["manual_repos"] if isinstance(x, str) and x.strip()]
        # 凭据: 新增(含 token)或删除
        action = body.get("cred_action")
        if action == "add":
            token = str(body.get("token") or "").strip()
            api_base = str(body.get("api_base") or "https://api.github.com").strip().rstrip("/")
            name = str(body.get("name") or "").strip() or "default"
            default = bool(body.get("default"))
            if not token:
                self._json({"ok": False, "error": "token 不能为空"}, 400)
                return
            config.add_credential(name, api_base, token, default, cfg)
            cfg = config.load()
        elif action == "remove":
            name = str(body.get("name") or "")
            api_base = str(body.get("api_base") or "")
            config.remove_credential(name, api_base, cfg)
            cfg = config.load()
        saved = config.save(cfg)
        self._json({"ok": True, "settings": self._public_settings_with_saved(saved)})

    def _public_settings_with_saved(self, saved):
        cfg = config.load()
        return self._public_settings()

    def _overview(self):
        cfg = config.load()
        repos = repo_scanner.discover(cfg)
        creds = github_api.discover_credentials(cfg.get("credentials"))
        lang = cfg.get("language", "auto")
        # 每个仓库并发查询云端状态
        results = []
        threads = []

        def work(repo):
            api_base, owner, repo_name = repo_scanner.repo_identity(repo)
            run = rel = None
            if owner and repo_name:
                client = None
                try:
                    cred = github_api.pick_credential(creds, api_base, owner)
                    tok = github_api.resolve_token(cred)
                    client = github_api.GitHubClient(api_base, token=tok)
                    run = client.latest_workflow_run(owner, repo_name)
                    rels = client.list_releases(owner, repo_name, 1)
                    rel = rels[0] if rels else None
                except Exception:
                    run = rel = None
            with threading.Lock():
                results.append({"repo": repo, "actions": run, "release": rel})

        for repo in repos:
            t = threading.Thread(target=work, args=(repo,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=25)
        results.sort(key=lambda x: x["repo"]["name"].lower())
        return {"repos": [x["repo"] for x in results],
                "cloud": {x["repo"]["name"]: {"actions": x["actions"], "release": x["release"]}
                          for x in results},
                "lang": lang,
                "has_credentials": bool(creds)}

    def _do_release(self, body):
        cfg = config.load()
        repo_path = body.get("path")
        version = body.get("version")
        # 找到对应本地仓库
        repos = repo_scanner.discover(cfg)
        target = next((r for r in repos if r.get("path") == repo_path), None)
        if not target:
            self._json({"ok": False, "error": "仓库不存在: %s" % repo_path}, 404)
            return
        ok, msg = release.release(target, version)
        self._json({"ok": ok, "msg": msg})


def _find_free_port(start):
    import socket as _s
    for port in range(start, start + 50):
        with _s.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _open_browser(url):
    try:
        if sys.platform.startswith("win"):
            os.startfile(url)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", url])
        else:
            import subprocess
            subprocess.Popen(["xdg-open", url])
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="GitHub 多仓库管理器")
    ap.add_argument("--port", type=int, default=None, help="监听端口(默认 8080, 冲突自动顺延)")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    cfg = config.load()
    port = args.port or cfg.get("port") or 8080
    port = _find_free_port(port)
    if port != (args.port or cfg.get("port") or 8080):
        cfg["port"] = port
        config.save(cfg)

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d" % port
    print("GitHub Repo Manager")
    print("  URL:  %s" % url)
    print("  设置: 扫描根目录 / 添加凭据(可复用 gh CLI 登录)")
    print("  退出: Ctrl+C")
    if not args.no_browser:
        _open_browser(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
