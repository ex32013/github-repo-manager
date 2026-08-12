# 经验教训总结

> 从 `github-actions-release-template`、`bilibili_downloader`、`视频裁剪工具`、`EPUB翻译`、`github_search`、`卡面生成`、`涤墨抹字`、`qBittorrent死链清理` 等项目中提炼。
> 目标：新项目 `github-repo-manager` 从第一天就规避这些坑。

---

## 一、安全类（最重，直接决定项目能不能用）

| # | 教训 | 来源案例 | 新项目对策 |
|---|---|---|---|
| S1 | 手写 HTTP 服务器**默认不安全**，不要假设"本地工具没关系" | bilibili/video-crop 均被审计出高危漏洞 | 安全清单第一天就位（见 PLAN.md 安全设计） |
| S2 | **白名单可自举**：`set-default-dir` 把任意目录加入白名单 → 任意文件读写删 | bilibili `/api/set-default-dir` + `_inside_downloads` 动态扩张 | 白名单固定或持久化授权，拒绝文件系统根 |
| S3 | **CSRF 前缀通配**：`host.startswith("127.")` 会被 `127.0.0.1.evil.com` 绕过 | bilibili + video-crop 的 `csrf_ok` | Origin 精确匹配，禁止前缀通配 |
| S4 | **XSS 内联拼接**：`escAttr` 只转义属性值，HTML 解码后进 JS 仍可逃逸 | bilibili index.html onclick 拼接文件名 | `jsStr()`(JSON.stringify+转义) + `escAttr()` 双保险，事件委托优先 |
| S5 | token 用 `==` 比较 → 时序侧信道；token 可能注入页面源码 | bilibili `auth_ok` / `index_html` | `secrets.compare_digest`；token 仅在有权限时注入 |
| S6 | body 无上限、超限不读直接响应 → 连接中断 + DoS | bilibili/video-crop `do_POST` | 1MB 上限 + 超限流式丢弃后再响应 |
| S7 | 日志/错误信息泄露路径、token、内部细节 | bilibili 错误消息带路径 | 统一脱敏，token 绝不打日志 |
| S8 | 上传/写入截断未检测 → 残缺文件被当成功 | video-crop `handle_upload` | 流式写盘 + 长度核对 + 失败清理 |

---

## 二、逻辑 / 并发类

| # | 教训 | 来源案例 | 新项目对策 |
|---|---|---|---|
| L1 | 工作线程**无 try/except 兜底** → 异常产生"僵尸任务"，永远删不掉 | bilibili `run_download_loop` | 所有后台线程整体 try/except，异常必落终态 |
| L2 | **暂停/终止与 Popen 竞态** → 卡死（Windows 下子进程继承管道句柄） | bilibili `task-pause` | reader 线程 + queue 轮询，终止用杀进程树 |
| L3 | 并发上限检查非原子 → 超发 | bilibili `_wait_for_slot` | LOCK 内完成"计数+置位" |
| L4 | resume/delete 幂等性缺失 → 双线程写同一文件 / 删掉后线程还在写 | bilibili `task-resume`/`task-delete` | 状态机原子迁移，删除前必须终态 |
| L5 | 存在判断想当然（只查 .mp4，audio/cover 永远"已存在"） | bilibili run_task | 按类型查对应扩展名 |
| L6 | 日志/列表无限增长 → 内存泄漏 | bilibili `log` | 条数上限（如 500） |

---

## 三、打包 / 发布 / CI 类

| # | 教训 | 来源案例 | 新项目对策 |
|---|---|---|---|
| P1 | **打包产物没验证就发布** → 发布出去的核心功能是坏的 | bilibili：PyInstaller 内嵌 yt-dlp 是坏命令，exe 下载功能不可用 | 打包后必须冒烟启动产物验证；CI 加"产物可运行"断言 |
| P2 | 外部命令依赖在打包后不存在 | bilibili 用 `subprocess` 调 `yt-dlp` 命令 | 打包前确认：内嵌引导程序 / 进程内 API / 明确运行时依赖 |
| P3 | tag 发布后移动 tag → `softprops/action-gh-release` 拒绝发布 | bilibili v1.4.2 release 失败 | workflow 只读 `GITHUB_REF_NAME`；checkout 锁 `github.sha` |
| P4 | workflow_dispatch 手动触发误用分支名当 tag | 模板仓库早期版本 | dispatch 加 `version` 输入，非 tag 触发不发布 |
| P5 | 第三方 action 未 pin commit SHA、依赖未锁版本 | 模板早期 | action pin SHA + 依赖锁版本 |
| P6 | 平台想当然：macOS 无 `xdg-open`、Linux 无回收站、`start /b` 关窗杀进程 | bilibili/video-crop | 平台分支显式处理 + 文档注明 |

---

## 四、工程 / 维护类

| # | 教训 | 来源案例 | 新项目对策 |
|---|---|---|---|
| E1 | **单文件过大难维护**（1700 行） | bili_server.py | 小文件拆分，按职责分模块 |
| E2 | **没有测试 → 每次审计都查出不同层新 bug** | 所有项目反复被审出逻辑/并发/安全/CI 问题 | 冒烟测试第一天就有，改动必跑 |
| E3 | README 与代码脱节（行为改了文档没改） | 手动触发行为改了，README 还写旧的 | 功能变更同步更新文档 |
| E4 | 需求不清就开写，边写边改 | 各项目 | 先规划落盘（PLAN.md），确认后再动工 |
| E5 | 版本管理混乱：tag 命名（v1.0.0 vs 1.0.0）、tag 移动 | video-crop tag 命名不统一 | 统一 `vX.Y.Z`，tag 一旦发布不移动 |
| E6 | 工具散落无文档，功能重复实现 | github_search/卡面生成 等一次性脚本 | 本项目集中管理 + README 说明 |

## 五、通用性 / 兼容性类（开源工具专属，最容易忽略）

> 前几轮只围绕本人环境设计（Windows、`E:\AI工具`、单账号），这是最大的方向错误。开源工具必须假设"任何开发者的机器"。

| # | 教训 | 新项目对策 |
|---|---|---|
| G1 | 写死本地路径（`E:\AI工具`）、假设单目录 | 仓库发现支持多根目录 + 手工添加 + 远端拉取三模式 |
| G2 | 假设只有 Windows、只有一个平台 | 路径用 pathlib，命令用 `git` 通用调用，三平台分派 open 命令 |
| G3 | 假设用户愿意去创建 token | 凭据多来源：优先复用 `gh` CLI 登录 → 环境变量 → 设置页输入 |
| G4 | 假设只有一个 GitHub 账号/主机 | 配置支持多凭据条目（个人+公司），预留 GitHub Enterprise（api_base 可配） |
| G5 | 只做中文，海外用户没法用 | 界面中/EN 双语，README 英文为主 |
| G6 | 假设用户熟读项目源码才能启动 | 零依赖 `python server.py` 即用，首次启动自动开浏览器，未配置时有引导不报错 |
| G7 | 假设端口永远空闲 | 端口冲突自动顺延 + 提示实际端口 |
| G8 | 没有开源协议、没有贡献指南 | LICENSE（MIT）+ 清晰文档，降低他人使用/贡献门槛 |

---

## 六、新项目最优先遵守的 7 条

1. **通用性第一**：任何功能先问"别的开发者环境能否用"（G1-G8）
2. **安全第一天就位**（S1-S8），不写"以后再补"
3. **测试第一天就有**（tests/smoke.py），改动必跑
4. **打包产物必须冒烟验证**（P1/P2）
5. **小文件拆分**，模块职责清晰（E1）
6. **先规划后动工**（E4），确认方案再写代码
7. **文档与代码同步**（E3），双语 README（G5）
