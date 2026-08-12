# -*- coding: utf-8 -*-
"""本地 git 仓库发现与状态采集。

发现模式:
- A. 扫描根目录(递归一层, 含隐藏目录, 支持多个根目录)
- B. 手工添加的仓库绝对路径
- C. 远端拉取(GitHub API 列出, 预留, Phase 2)

每个仓库采集: 本地HEAD / 远端HEAD / 未推送提交数 / git status 摘要 / remote origin url。
"""
import os
import re
import subprocess


def _git(root, args, timeout=20):
    try:
        r = subprocess.run(["git", "-C", root] + args, capture_output=True,
                           text=True, timeout=timeout, check=False,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def is_git_repo(path):
    if not os.path.isdir(path):
        return False
    rc, _, _ = _git(path, ["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and True


def _remote_url(path):
    rc, out, _ = _git(path, ["config", "--get", "remote.origin.url"])
    return out if rc == 0 and out else None


def _head_commits(path):
    """返回 (本地HEAD短, 远端HEAD短, 未推送提交数, 是否领先)。失败返回 None。"""
    rc, out, _ = _git(path, ["rev-parse", "--short", "HEAD"])
    if rc != 0 or not out:
        return None
    local = out
    rc2, branch, _ = _git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch if rc2 == 0 else None
    remote = None
    ahead = 0
    if branch and branch != "HEAD":
        rc3, rsha, _ = _git(path, ["rev-parse", "--short", "origin/" + branch])
        if rc3 == 0 and rsha:
            remote = rsha
            rc4, aout, _ = _git(path, ["rev-list", "--count", "origin/" + branch + "..HEAD"])
            if rc4 == 0:
                ahead = int(aout or 0)
    return {"local": local, "remote": remote, "ahead": ahead, "branch": branch}


def _git_status(path):
    """git status --short 精简摘要: 改动/新增/删除/未跟踪 计数。"""
    rc, out, _ = _git(path, ["status", "--short"])
    if rc != 0:
        return {"changed": 0, "untracked": 0, "lines": 0}
    lines = [l for l in out.splitlines() if l.strip()] if out else []
    changed = sum(1 for l in lines if l[:2].strip() not in ("", "?"))
    untracked = sum(1 for l in lines if l[:1] == "?")
    return {"changed": changed, "untracked": untracked, "lines": len(lines)}


def discover(config):
    """扫描本地 git 仓库。返回仓库对象列表(按目录名排序)。"""
    roots = [os.path.abspath(r) for r in (config.get("root_dirs") or []) if r.strip()]
    manual = [os.path.abspath(r) for r in (config.get("manual_repos") or []) if r.strip()]
    seen = set()
    found = []

    def add_dir(path):
        if path in seen:
            return
        seen.add(path)
        if is_git_repo(path):
            found.append(path)

    for root in roots:
        if os.path.isdir(root):
            add_dir(root)
            try:
                for name in os.listdir(root):
                    full = os.path.join(root, name)
                    if os.path.isdir(full) and not os.path.islink(full):
                        add_dir(full)
            except OSError:
                pass
    for path in manual:
        add_dir(path)

    repos = []
    for path in found:
        remote = _remote_url(path)
        head = _head_commits(path)
        status = _git_status(path) if head else None
        repos.append({
            "path": path,
            "name": os.path.basename(path),
            "remote": remote,
            "head": head,
            "status": status,
        })
    repos.sort(key=lambda r: r["name"].lower())
    return repos


_OWNER_RE = re.compile(r"(?:github\.com[:/])([^/]+)/")
_ENDPOINT_RE = re.compile(r"https?://([^/]+)/")


def repo_identity(repo):
    """从 remote url 推断 (api_base, owner, repo_name)。用于匹配凭据与云端查询。
    无法推断时返回 (None, None, None)。"""
    remote = repo.get("remote")
    if not remote:
        return None, None, None
    # 处理 ssh (git@host:owner/repo.git) 与 https (https://host/owner/repo.git)
    if remote.startswith("git@"):
        rest = remote[4:]
        host, _, path = rest.partition(":")
    elif "://" in remote:
        m = _ENDPOINT_RE.match(remote)
        if not m:
            return None, None, None
        host = m.group(1)
        path = remote[m.end():]
    else:
        return None, None, None
    path = path.rstrip("/").rstrip(".git")
    parts = path.split("/")
    if len(parts) < 2:
        return None, None, None
    owner = parts[-2]
    repo_name = parts[-1]
    api_base = "https://api.github.com" if host.lower() in ("github.com", "www.github.com") \
        else ("https://" + host + "/api/v3")
    return api_base, owner, repo_name
