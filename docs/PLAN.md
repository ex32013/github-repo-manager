# github-repo-manager — 本地 GitHub 多仓库管理器

本地 Web 工具，集中管理多个 GitHub 项目：仓库总览、Actions 巡检、Release 一览、一键发版。

> 状态：**规划阶段**（Phase 1 未开工）
> 定位：面向**通用开发者**的开源工具（Windows / Linux / macOS），任何人可下载即用。

---

## 📌 项目定位

- **解决什么问题**：开发者维护多个 GitHub 仓库时，需要频繁在多个网页间切换——看 Actions 状态、查 Release、手动打 tag 发版。本工具把这些集中到一个本地界面。
- **使用者**：任何使用 GitHub 的开发者，不局限于本机环境。
- **技术栈**：Python 3.8+（标准库为主，http.server）+ 单页前端 + GitHub REST API + 本地 git。
- **零第三方依赖**：后端只用标准库，前端纯原生 JS。让任何人 `pip` 之外无需额外安装即可运行。

---

## 🌍 通用性设计（核心原则）

> 不能假设用户是 Windows、在中国大陆、只有一个 GitHub 账号、仓库放在某个固定目录。以下每个维度都按"多数开发者环境"设计，并提供配置化覆盖。

### 1. 跨平台

- **Windows / Linux / macOS 全支持**（git + Python 3.8+ 即可）
- 路径处理一律 `os.path`/`pathlib`，不用硬编码反斜杠
- git 命令通过 `git` 可执行文件调用（三平台通用），不假设 `git.exe` 位置
- 打开浏览器/文件夹按平台分派（Windows `start`、macOS `open`、Linux `xdg-open`）
- 后续可打包成 3 平台 exe（复用 release 模板）

### 2. 仓库发现（多模式，不假设目录）

| 模式 | 说明 | 适用场景 |
|---|---|---|
| **A. 扫描目录** | 递归扫描用户指定根目录下的 git 仓库（可配多个根目录） | 本地克隆集中管理的用户 |
| **B. 手工添加** | 用户手动添加仓库绝对路径 | 仓库分散在不同位置 |
| **C. 远端拉取** | 通过 GitHub API 拉取用户名下/org 下所有仓库列表，并显示其云端状态 | 本地未克隆也可见 |

三种模式可组合。仓库去重按 `git remote origin url` 归一化（ssh/https/git 协议算同一个）。

### 3. 凭据（多来源，不强制用户去创建 token）

按优先级自动探测，用户也可在设置页手动配置：

1. **gh CLI 已登录**（`gh auth status`）→ 直接复用 `gh auth token`，零配置
2. **环境变量 `GITHUB_TOKEN` / `GH_TOKEN`** → 常见 CI/本机约定
3. **设置页手动输入** → 存入本地配置文件（权限保护），支持 fine-grained PAT
4. **未配置** → 只读公共仓库可用，私有仓库提示配置；`POST /api/release` 等写操作明确要求凭据

### 4. 多账号 / 多主机

- 配置支持**多个凭据条目**（如个人 + 公司账号），按仓库的 `origin` 主机 + owner 自动匹配
- 预留 **GitHub Enterprise** 支持：凭据条目带 `api_base`（默认 `https://api.github.com`），同一套 API 层可指向任意 GHE 实例

### 5. 本地化

- 界面支持**中 / EN** 切换（复用 video-crop 的语言方案），默认跟随浏览器语言
- README 中英双语（英文为主，适配全球用户）

### 6. 开箱即用

- `pip install` 可选；零依赖直接 `python server.py` 可跑
- 首次启动自动打开浏览器；未配置凭据时页面有清晰引导（不报错卡死）
- 端口冲突自动顺延（如 8080 → 8081 → ...）并提示实际端口

---

## 📁 项目结构

```
github-repo-manager/
├── server.py           # 后端入口: 静态服务 + API 路由
├── github_api.py       # GitHub API 封装(多主机/多凭据/重试限流)
├── repo_scanner.py     # 本地 git 仓库发现(目录扫描/手工/远端)+ 状态
├── release.py          # 发版逻辑(打 tag/push, 复用用户已有 workflow)
├── config.py           # 配置读写(多凭据/多根目录/语言, 权限保护)
├── i18n.py             # 中/英文案
├── index.html          # 前端单页
├── tests/
│   └── smoke.py        # 冒烟测试
├── docs/
│   ├── PLAN.md         # 完整规划
│   └── LESSONS.md      # 经验教训总结
├── README.md           # 中英双语使用说明
├── LICENSE             # 开源协议
├── .gitignore
└── pyproject.toml      # 可选: pip install 打包入口
```

---

## 🎯 功能规划（分 3 阶段）

### Phase 1 — 只读总览（MVP）

| 功能 | 说明 | API |
|---|---|---|
| 仓库列表 | 三种发现模式组合，显示本地HEAD/远程HEAD/未推送提交数 | `GET /api/repos` |
| Actions 巡检 | 每仓库最新 workflow run 状态，失败标红+失败步骤 | `GET /api/actions` |
| 本地状态 | git status 精简摘要（改动/未跟踪文件数） | `GET /api/repos` 附带 |
| 设置页 | 配置根目录/凭据/语言 | `GET/POST /api/settings` |

### Phase 2 — 管理操作

| 功能 | 说明 | API |
|---|---|---|
| Release 列表 | 每仓库最近 Release（版本号/时间/产物数） | `GET /api/releases` |
| 一键发版 | 填版本号 → 打 tag + push → 触发 workflow → 轮询状态 | `POST /api/release` |
| 批量刷新 | 一键重拉所有仓库状态 | `POST /api/refresh` |

### Phase 3 — 增强（可选，暂缓）

- 打包 exe（3 平台）
- GitHub Enterprise 深入支持
- 通知、历史记录

---

## 🔐 安全设计（从第一天就内置）

1. **只监听 127.0.0.1**，默认不暴露局域网（`--host` 显式开启）
2. **CSRF**：Origin/Referer 精确匹配本机地址，**禁止 `127.*` 前缀通配**（堵 DNS-rebinding）
3. **凭据保护**：本地文件 + 权限（POSIX 0600 / Windows 用户目录）；`secrets.compare_digest` 比较；**绝不打日志**
4. **body 上限**：1MB，超限流式丢弃后响应 413
5. **前端渲染**：统一 `esc()` + `jsStr()` 双保险，禁止裸拼 innerHTML 传用户数据
6. **写操作强制二次确认**（发版等）
7. **响应头**：`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`
8. **错误脱敏**：不泄露路径/凭据/内部细节

---

## 🧪 测试防线

- `tests/smoke.py` 覆盖：主页 200、凭据缺失 401、CSRF 恶意 Origin 拒绝、超大 body 413、仓库扫描合法结构
- **三平台 CI**（复用 release 模板）：每次 push 跑 smoke + 打包后冒烟启动产物
- 本地改动必跑测试

---

## 📅 开发顺序

1. 规划落盘（PLAN + LESSONS）✅
2. 骨架：config.py（多凭据/多根目录）+ server.py 静态服务 + i18n
3. Phase 1：repo_scanner（三模式）→ github_api（多主机）→ API → 前端
4. tests/smoke.py 跑通
5. Phase 2：release.py → 发版 UI
6. README 双语 + LICENSE
7. 可选：打包 + CI

---

## ⏱ 工作量预估

| 阶段 | 预估 |
|---|---|
| Phase 1（只读 MVP，含通用性） | 3-5 小时 |
| Phase 2（发版） | 2-3 小时 |
| 测试 + 打磨 + 文档 | 2-3 小时 |
| 打包 + CI（可选） | 另加 |

---

## ❓ 需要确认的决策点

1. **凭据优先级**：是否支持复用 `gh` CLI 登录（推荐，零配置）？还是仅手动输入 token？
2. **远端仓库模式**（C）：是否要"未克隆也列出云端仓库"？还是只管理本地已克隆的仓库？
3. **多主机**：是否需要现在就支持 GitHub Enterprise，还是先只做 github.com、预留扩展？
4. **许可证**：选哪个开源协议（MIT 推荐）？
