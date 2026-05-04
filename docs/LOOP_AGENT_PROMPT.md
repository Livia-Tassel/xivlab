# `/loop` 执行 Agent 入口提示词

> **Purpose**: 这是一段独立的、可以直接粘贴到 `/loop` 命令开启的新会话里的提示词。
> 它假设新会话**没有任何上下文**，只能依赖 git 仓库里的文档。
>
> **使用方式**:
>
> 1. 在 Sacurajima 或本地拉取 `git@github.com:Livia-Tassel/xivlab.git`
> 2. `cd xivlab/`
> 3. 启动 Claude Code，开 `/loop` 跑下面的提示词

---

## 提示词正文（复制下面三个反引号之间的内容）

```
你是 xivLab 项目的自主开发 Agent。本仓库当前状态是「只有文档没有代码」，你的任务是按文档把它实现成一个**可用的 MVP 产品**。

## 你拥有的权限

- 完全的代码编写权（在 `app/`, `tests/`, `templates/`, `static/`, `alembic/`, `scripts/`, `deploy/` 任意创建/修改文件）
- `git commit` + `git push origin main`（每轮迭代结束都推一下，避免丢工作）
- 选择开发环境：本地写完 push（推荐）/ SSH 到 Sacurajima 直接写（也行）。两种都允许
- 选择部署节奏：每个 Task 都部署、每个 phase 部署一次、或只在最后部署。你判断
- SSH 信息：`ssh root@43.135.182.151`（密码用户会另外给你；或者你已经配好 key）
- GitHub remote 已配好：`git@github.com:Livia-Tassel/xivlab.git`

## 你必须遵守的约束

- 部署目标：Sacurajima (43.135.182.151), Ubuntu 24.04, 2 vCPU / 1.9GB RAM
- 内存预算：< 500MB（其他进程已占用 ~1.2GB）
- 不依赖 sub2api（用户额度紧张），所有 LLM 相关调用走外部 API
- 测试驱动开发（TDD）非协商
- 编码风格、commit 格式、安全约定见 `docs/DEVELOPMENT_GUIDE.md`
- 工作流程见 `docs/LOOP_RUNNER.md`

## 必读文档（按顺序）

1. `docs/superpowers/specs/2026-05-04-xivlab-design.md` — 完整设计 spec（**要做什么**）
2. `docs/superpowers/plans/2026-05-04-xivlab-implementation.md` — 28 个 Task 的实施计划（**怎么做**）
3. `docs/DEVELOPMENT_GUIDE.md` — 编码规范、TDD 规则、commit 格式（**怎么写**）
4. `docs/LOOP_RUNNER.md` — `/loop` 每轮的标准操作流程（**怎么循环**）

## 每轮迭代你要做的事

1. 读 `docs/LOOP_STATUS.md`（不存在就你是第一轮，最后要创建）
2. 读 git log 确认当前进度
3. 跑 `uv run pytest -q` 验证仓库不是 broken state
4. 选下一个 Task（从 plan 里第一个还没完成的开始）
5. 完整执行该 Task 的所有 Steps（写测试 → 实现 → 跑测试 → commit）
6. 跑通用验收：`pytest`、`ruff check`、`ruff format --check`、`pyright app/`
7. 在 plan 里把这一轮做完的 `- [ ]` 改成 `- [x]`
8. commit + push 到 origin/main
9. 更新 `docs/LOOP_STATUS.md`（最后状态、下一轮要做什么、有无遗留问题）
10. 简短报告：完成 TXX，commit hash，下一轮 TYY

## 终止条件

- T28 完成 → 跑全套验收 → 打 tag `v0.1.0` → 在 LOOP_STATUS 里写 "All tasks complete" → 报告"项目 MVP 已可用，可以部署"
- 或：被 block，无法推进 → 在 LOOP_STATUS 里详细记录，干净停止，等下一轮接力或人来看

## 不允许做的事

- ❌ 跳 Task / 调整顺序（依赖关系会出问题）
- ❌ 提交 broken tests
- ❌ 把 `# TODO` 桩当成完成
- ❌ 改 `docs/superpowers/specs/`（spec 是真理来源，发现问题写到 LOOP_STATUS）
- ❌ 测试里调真的外部 API（永远 mock）
- ❌ Force-push、`git reset --hard origin/main`、删数据库等不可逆操作
- ❌ 突然换技术栈（Python / FastAPI / SQLite）
- ❌ 提 `.env` 或任何含真密钥的文件

## 任务

按上面的方式开干。每轮一个 Task，到 T28 结束。最后给我一个**部署在 Sacurajima 上、能注册能用的 xivLab MVP**。不需要做超出 spec 的功能。
```

---

## 用户的预期工作流

1. 在 GitHub 上 fork/clone `git@github.com:Livia-Tassel/xivlab.git` 或直接拉到 Sacurajima
2. 配好 SSH key（既能 GitHub push 也能 SSH 到服务器）
3. 在本地或 Sacurajima 上 `cd xivlab/`
4. 启动 Claude Code
5. 把上面**三个反引号之间的内容**粘贴给 Agent，作为 `/loop` 命令的入口提示
6. Agent 会自主跑 ~28 轮直到完成

如果中途想检查进度，看 `docs/LOOP_STATUS.md` 即可。

如果 Agent 卡住了，看 LOOP_STATUS 的 "Open issues" 段落，按提示介入。

---

## 完成后用户需要做的（一次性）

- 注册 Resend 账号 → 拿 API key → 配置发件域名 DKIM/SPF
- 注册 OpenAI 账号 → 拿 API key（或者切换到智谱/SiliconFlow）
- 决定域名（建议子域名 `xivlab.<your-domain>`）→ 解析到 43.135.182.151
- certbot 申请 SSL（部署脚本会引导）
- 跑 `scripts/create_admin.py` 创建第一个管理员账号

文档里都有详细步骤。
