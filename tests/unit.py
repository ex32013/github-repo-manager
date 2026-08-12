# -*- coding: utf-8 -*-
"""单元测试: github_api 的凭据匹配 / URL 解析(不依赖网络)。
运行: python tests/unit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import github_api


def test_pick_credential():
    creds = [
        {"name": "personal", "api_base": "https://api.github.com", "default": True},
        {"name": "work", "api_base": "https://ghe.corp.com/api/v3", "default": False},
    ]
    # github.com 下 owner 匹配
    c = github_api.pick_credential(creds, "https://api.github.com", "ex32013")
    assert c and c["name"] == "personal", "github.com 应匹配 personal"
    # 默认匹配
    c = github_api.pick_credential(creds, "https://api.github.com", "someone")
    assert c and c["name"] == "personal", "github.com 无 owner 匹配应回退默认"
    # GHE 主机
    c = github_api.pick_credential(creds, "https://ghe.corp.com/api/v3", "team")
    assert c and c["name"] == "work", "GHE 应匹配 work"
    # 空凭据
    assert github_api.pick_credential([], "https://api.github.com", "x") is None


def test_owner_from_url():
    assert github_api._owner_from_url("git@github.com:ex32013/bili.git") == "ex32013"
    assert github_api._owner_from_url("https://github.com/ex32013/bili.git") == "ex32013"
    assert github_api._owner_from_url("https://ghe.corp.com/team/tool.git") == "team"
    assert github_api._owner_from_url("") is None
    assert github_api._owner_from_url("not-a-url") is None


def test_api_base_detection():
    # github.com → 官方 API
    assert github_api.GitHubClient("https://api.github.com").api_base == "https://api.github.com"
    # GHE → 前缀校验
    c = github_api.GitHubClient("https://ghe.corp.com/api/v3/")
    assert c.api_base == "https://ghe.corp.com/api/v3"


def test_discover_credentials_dedup():
    cfg = [{"name": "personal", "api_base": "https://api.github.com", "token": "x"}]
    out = github_api.discover_credentials(cfg)
    names = [c["name"] for c in out]
    # 配置的 personal 存在, 且不重复
    assert names.count("personal") == 1, "应去重: %s" % names


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for t in tests:
        try:
            t()
            print("PASS  ", t.__name__)
        except AssertionError as e:
            fails += 1
            print("FAIL  ", t.__name__, "->", e)
        except Exception as e:
            fails += 1
            print("ERROR ", t.__name__, "->", type(e).__name__, e)
    if fails:
        sys.exit(1)
    print("\nUNIT OK: %d passed" % len(tests))
