# -*- coding: utf-8 -*-
"""一键发版: 本地打 tag + push, 触发用户的 release workflow。"""
import os
import re
import subprocess


def _git(root, args, timeout=60):
    try:
        r = subprocess.run(["git", "-C", root] + args, capture_output=True,
                           text=True, timeout=timeout, check=False,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-.][0-9A-Za-z]+)*$")


def validate_version(version):
    """校验版本号格式: 允许 v1.2.3 或 1.2.3(-beta 等后缀)。返回 (ok, 规范化的 tag)。"""
    v = (version or "").strip()
    if not v:
        return False, "版本号不能为空"
    if not TAG_RE.match(v):
        return False, "版本号格式应为 v1.2.3 或 1.2.3"
    tag = v if v.startswith("v") else "v" + v
    return True, tag


def release(repo, version, dry_run=False):
    """对本地仓库打 tag 并 push 到 origin。
    返回 (ok, 消息)。push 使用系统 git 凭据。"""
    ok, tag = validate_version(version)
    if not ok:
        return False, tag
    path = repo.get("path")
    if not path:
        return False, "仓库路径缺失"
    rc, _, _ = _git(path, ["remote", "get-url", "origin"])
    if rc != 0:
        return False, "仓库没有 origin 远端"

    # 本地是否有未提交改动? 发版最好基于干净工作区, 但允许(打 tag 不影响)。仅提示。
    rc2, out, _ = _git(path, ["status", "--short"])
    dirty = rc2 == 0 and bool(out.strip())

    # 检查 tag 是否已存在
    rc3, out3, _ = _git(path, ["tag", "-l", tag])
    if rc3 == 0 and out3.strip():
        return False, "tag %s 已存在" % tag

    if dry_run:
        return True, "dry-run 通过: 将打 tag %s 并 push(工作区%s)" % (
            tag, "有未提交改动" if dirty else "干净")

    rc4, _, err4 = _git(path, ["tag", tag])
    if rc4 != 0:
        return False, "打 tag 失败: " + err4
    rc5, _, err5 = _git(path, ["push", "origin", tag])
    if rc5 != 0:
        # 回滚已打的本地产
        _git(path, ["tag", "-d", tag])
        return False, "推送 tag 失败: " + err5
    return True, "已发布 %s (tag %s)" % (repo.get("name"), tag)
