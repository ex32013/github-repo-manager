# -*- coding: utf-8 -*-
"""GitHub REST API 封装。

特性:
- 凭据探测优先级: 显式 token(设置页) > 环境变量 GITHUB_TOKEN/GH_TOKEN > gh CLI 复用
- api_base 参数化(默认 api.github.com, 天然支持 GitHub Enterprise)
- 多凭据按 api_base + 仓库 owner 匹配
- 请求重试(网络抖动)、限流(Rate Limit)自动等待
- token 绝不打日志
"""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

_TIMEOUT = 30
_lock = threading.Lock()


def _gh_auth_token():
    """尝试复用 gh CLI 的登录 token。失败返回 None。"""
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                           timeout=15, check=False)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def resolve_token(cred):
    """给定配置凭据条目, 返回可用 token(或 None)。
    优先级: 条目内 token > 环境变量(同 api_base) > gh CLI(仅 github.com)。"""
    if cred and cred.get("token"):
        return cred["token"]
    base = (cred or {}).get("api_base") or "https://api.github.com"
    if "api.github.com" in base:
        env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if env:
            return env
        return _gh_auth_token()
    return None


def discover_credentials(configured):
    """返回可用凭据列表: 配置的 + 环境变量/gh 自动探测到的 github.com 凭据(去重)。"""
    out = list(configured or [])
    seen = {(c.get("api_base"), c.get("name")) for c in out}
    # 探测 github.com 是否有环境变量/gh 凭据可用
    auto = _auto_github_cred()
    if auto and (auto["api_base"], auto["name"]) not in seen:
        out.append(auto)
    return out


def _auto_github_cred():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or _gh_auth_token()
    if not tok:
        return None
    return {"name": "auto(env/gh)", "api_base": "https://api.github.com",
            "token": tok, "default": False, "auto": True}


def pick_credential(creds, api_base, owner):
    """按主机+owner 匹配凭据: 优先匹配该 api_base 下名为 owner 的; 否则该主机默认; 否则任意主机默认。"""
    if not creds:
        return None
    base = api_base or "https://api.github.com"
    same_base = [c for c in creds if (c.get("api_base") or "https://api.github.com") == base]
    for c in same_base:
        if c.get("name") == owner:
            return c
    for c in same_base:
        if c.get("default"):
            return c
    if same_base:
        return same_base[0]
    for c in creds:
        if c.get("default"):
            return c
    return creds[0]


def _owner_from_url(remote_url):
    """从 remote url 提取 owner (宽松匹配, 失败返回 None)。
    支持 ssh: git@github.com:owner/repo.git; https: https://host/owner/repo.git。"""
    u = (remote_url or "").strip()
    if not u:
        return None
    if u.startswith("git@"):
        rest = u[4:]
        path = rest.split(":", 1)[1] if ":" in rest else ""
    elif "://" in u:
        m = re.search(r"://[^/]+/(.+)$", u)
        path = m.group(1) if m else ""
    else:
        path = u
    path = path.rstrip("/").rstrip(".git")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return parts[-2]
    return None


class APIError(Exception):
    pass


class GitHubClient:
    def __init__(self, api_base="https://api.github.com", token=None, verify=True):
        self.api_base = (api_base or "https://api.github.com").rstrip("/")
        self.token = token
        self.verify = verify

    def _headers(self):
        h = {"Accept": "application/vnd.github+json",
             "User-Agent": "github-repo-manager"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _url(self, path):
        return self.api_base + path

    def _request(self, method, path, body=None, retries=2):
        url = self._url(path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers())
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                    raw = r.read()
                    if r.status == 204:
                        return None
                    return json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 403 and "rate limit" in (e.headers.get("X-RateLimit-Remaining") or "").lower() and attempt < retries:
                    reset = int(e.headers.get("X-RateLimit-Reset") or "0") or int(time.time()) + 5
                    time.sleep(min(reset - time.time() + 1, 60))
                    continue
                if e.code == 401:
                    raise APIError("unauthorized")
                if e.code == 404:
                    raise APIError("not_found")
                raise APIError("http_%d" % e.code)
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise APIError("network: %s" % e.reason)
        raise APIError("unreachable")

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, body=None):
        return self._request("POST", path, body)

    # ---- 常用 API ----
    def latest_workflow_run(self, owner, repo):
        """返回最新一次 workflow run 摘要, 无则 None。"""
        data = self.get("/repos/%s/%s/actions/runs?per_page=1" % (owner, repo))
        runs = (data or {}).get("workflow_runs") or []
        if not runs:
            return None
        r = runs[0]
        return {"name": r.get("name"), "status": r.get("status"),
                "conclusion": r.get("conclusion"), "head_sha": (r.get("head_sha") or "")[:7],
                "created_at": r.get("created_at"), "run_number": r.get("run_number"),
                "url": r.get("html_url")}

    def list_releases(self, owner, repo, per_page=5):
        data = self.get("/repos/%s/%s/releases?per_page=%d" % (owner, repo, per_page))
        if not isinstance(data, list):
            return []
        return [{"tag_name": x.get("tag_name"), "name": x.get("name"),
                 "published_at": x.get("published_at"), "html_url": x.get("html_url"),
                 "assets": len(x.get("assets") or [])} for x in data]

    def _get_paged(self, path_fmt, per_page=100, max_pages=10):
        """自动翻页收集。path_fmt 需含 {page} 占位, 如 '/user/repos?per_page={per_page}&page={page}'。"""
        items = []
        page = 1
        while page <= max_pages:
            path = path_fmt.format(page=page, per_page=per_page)
            data = self.get(path)
            if not isinstance(data, list) or not data:
                break
            items.extend(data)
            if len(data) < per_page:
                break
            page += 1
        return items

    def list_user_repos(self, per_page=100):
        """列出当前凭据可见的所有仓库(自动分页)。"""
        data = self._get_paged(
            "/user/repos?sort=updated&per_page={per_page}&page={page}", per_page=per_page)
        return [{"full_name": x.get("full_name"), "default_branch": x.get("default_branch"),
                 "private": x.get("private"), "updated_at": x.get("updated_at"),
                 "html_url": x.get("html_url"),
                 "clone_url": x.get("clone_url"),
                 "ssh_url": x.get("ssh_url"),
                 "description": x.get("description"),
                 "language": x.get("language"),
                 "stargazers_count": x.get("stargazers_count", 0)} for x in data]

    def repo_details(self, owner, repo):
        """单个仓库详情(含 clone_url, 用于一键克隆)。"""
        data = self.get("/repos/%s/%s" % (owner, repo))
        return {"full_name": data.get("full_name"), "default_branch": data.get("default_branch"),
                "private": data.get("private"), "clone_url": data.get("clone_url"),
                "ssh_url": data.get("ssh_url"), "language": data.get("language"),
                "description": data.get("description")}


def build_clients(creds, api_base=None, owner=None):
    """按 api_base+owner 建客户端列表。返回 [(client, cred)]。"""
    cred = pick_credential(creds, api_base, owner)
    if not cred:
        base = api_base or "https://api.github.com"
        return [(GitHubClient(base, token=None), None)]
    base = cred.get("api_base") or "https://api.github.com"
    tok = resolve_token(cred)
    return [(GitHubClient(base, token=tok), cred)]
