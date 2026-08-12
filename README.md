# GitHub Repo Manager

Manage all your GitHub repositories from one local web UI — repo overview, Actions status, Releases, and one-click release.

用本地 Web 界面集中管理你的多个 GitHub 仓库 —— 仓库总览、Actions 状态、Release 列表、一键发版。

## Features / 功能

- **Repo overview** — scans local git repos, shows local/remote commit, unpushed commits, dirty state
- **Actions status** — latest workflow run per repo (success/failure/running)
- **Releases** — latest version per repo with link
- **Cloud mode** — lists all repos under your credentials, marks which are cloned, one-click clone
- **One-click release** — tag + push to trigger your release workflow (single or batch)
- **Multi-platform** — Windows / Linux / macOS (requires only Python 3.8+ and git)
- **Zero dependencies** — standard library only, no pip installs needed
- **Multi-account / GHE-ready** — multiple credentials, `api_base` parameterized for GitHub Enterprise

- **仓库总览** — 扫描本地 git 仓库，显示本地/远端 commit、未推送提交、本地改动
- **Actions 巡检** — 每仓库最新 workflow 状态（成功/失败/运行中）
- **Release 一览** — 每仓库最新版本
- **云端模式** — 列出凭据下所有仓库，标注本地是否已克隆，支持一键克隆
- **一键发版** — 打 tag + push（单仓库或勾选批量），触发你的 release workflow
- **多平台** — Windows / Linux / macOS（只需 Python 3.8+ 和 git）
- **零依赖** — 只用标准库，无需 pip 安装任何包
- **多账号 / 预留 GHE** — 支持多凭据，`api_base` 参数化可指向 GitHub Enterprise

## Quick start / 快速开始

```bash
python server.py
# open http://127.0.0.1:8080
```

First run: open **Settings** → add scan root dirs (or manual repos) → credentials are optional (see below).

首次使用：打开**设置**页 → 配置扫描根目录（或手工添加仓库）→ 凭据可选（见下）。

## Credentials / 凭据

Credentials are resolved in priority order / 凭据按优先级自动探测：

1. **gh CLI login** — if you have `gh auth login` done, it's reused automatically / 已登录 `gh` 则自动复用
2. **Env vars** — `GITHUB_TOKEN` / `GH_TOKEN` / 环境变量
3. **Manual** — add token in Settings / 在设置页手动添加

Tokens are stored in `~/.github-repo-manager/config.json` with restricted permissions. Never logged.
token 存于 `~/.github-repo-manager/config.json`（权限受保护），绝不打入日志。

Without credentials: public repos' Actions/Releases are unavailable; private repos are not listed.
未配置凭据：公共仓库的 Actions/Release 不可用；私有仓库不显示。

## API overview / API 一览

| Method | Path | Description |
|---|---|---|
| GET | `/api/settings` | current config (no token) / 当前配置（不含 token） |
| POST | `/api/settings` | save settings / add / remove credential |
| GET | `/api/repos` | local repo scan / 本地仓库扫描 |
| GET | `/api/overview` | repos + Actions + Releases summary / 总览 |
| GET | `/api/cloud-repos` | cloud repos under credentials (cloned marked) / 云端仓库 |
| POST | `/api/clone` | git clone a cloud repo / 一键克隆 |
| POST | `/api/release` | tag + push a version (single or batch) / 打 tag 发版 |

## Security / 安全

- Binds to `127.0.0.1` only / 默认仅监听本机
- CSRF protection with exact-origin matching (no `127.*` prefix wildcard) / CSRF 精确匹配
- Request body capped at 1 MB / body 上限 1MB
- No-store cache headers / 禁止缓存
- All rendering escaped (no XSS) / 前端渲染全转义

## Project structure / 项目结构

```
├── server.py           # HTTP server + API routes
├── github_api.py       # GitHub REST client (multi-host, gh reuse, retry/rate-limit)
├── repo_scanner.py     # local git repo discovery + status
├── release.py          # one-click release (tag + push)
├── config.py           # config persistence (credentials, roots, language)
├── i18n.py             # zh/en strings
├── index.html          # single-page frontend
├── tests/
│   ├── smoke.py        # smoke tests (HTTP API)
│   └── unit.py         # unit tests (credential matching, URL parsing)
└── .github/workflows/release.yml  # build exe + CI
```

## Development / 开发

```bash
python tests/smoke.py   # run smoke tests
python tests/unit.py    # run unit tests
```

## License

[MIT](LICENSE)
