# -*- coding: utf-8 -*-
"""配置读写: 多凭据条目 / 多根目录 / 语言。token 存本地文件并做权限保护。"""
import json
import os
import stat

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".github-repo-manager")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "language": "auto",       # auto / zh / en
    "root_dirs": [],          # 扫描根目录列表
    "manual_repos": [],       # 手工添加的仓库绝对路径
    "credentials": [],        # [{"name","api_base","token","default":bool}]
    "port": 8080,
    "verify": True,           # 是否校验 TLS 证书
}


def _ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    # POSIX 上限制目录权限 0700, 保护其中的 token
    if os.name != "nt":
        try:
            os.chmod(CONFIG_DIR, stat.S_IRWXU)
        except OSError:
            pass


def _secure_perms(path):
    """POSIX 下把配置文件权限设为 0600"""
    if os.name != "nt" and os.path.exists(path):
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
    return cfg


def save(cfg):
    _ensure_config_dir()
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)
    _secure_perms(CONFIG_FILE)
    return merged


def add_credential(name, api_base, token, default=False, current=None):
    """新增/更新凭据条目。同名(api_base+name)则更新, 否则追加。"""
    cfg = current or load()
    creds = [c for c in cfg.get("credentials", []) if c.get("api_base") != api_base
             or c.get("name") != name]
    creds.append({"name": name, "api_base": api_base, "token": token,
                  "default": bool(default)})
    # 若设为默认, 清除其他默认
    if default:
        for c in creds:
            c["default"] = False
        creds[-1]["default"] = True
    elif not any(c.get("default") for c in creds):
        creds[0]["default"] = True
    cfg["credentials"] = creds
    return save(cfg)


def remove_credential(name, api_base, current=None):
    cfg = current or load()
    cfg["credentials"] = [c for c in cfg.get("credentials", [])
                          if not (c.get("api_base") == api_base and c.get("name") == name)]
    return save(cfg)
