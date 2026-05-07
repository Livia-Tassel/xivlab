# xivLab 🧪

> 为科研人定制的 AI 工具站 — arXiv 早报 + 科研 prompt 社区

## 状态

✅ **MVP 实现中**。代码已贯通主流程；正在收尾测试与部署。

## Modules

- **arXiv 早报** — 个性化论文订阅 + 推送（每用户 2 个 task，关键词+语义筛选，Email + RSS）
- **PromptHub** — 科研场景 AI prompt 的开源社区（9 大分类，点赞排序，社区驱动）

## Tech stack

Python 3.12 · FastAPI · SQLAlchemy 2 (async) · SQLite + sqlite-vec · Jinja2 · HTMX · Tailwind · APScheduler · Resend (email) · OpenAI SDK (embeddings)

## Quickstart

```bash
# 安装依赖
uv sync

# 初始化数据库
uv run alembic upgrade head

# 启动开发服务（http://localhost:8001）
uv run uvicorn app.main:app --reload --port 8001
```

## Development

```bash
# 测试
uv run pytest -v

# 静态检查
uv run ruff check app/ tests/
uv run ruff format --check app/ tests/
uv run pyright app/
```

环境变量参考 `.env.example`。开发环境默认使用 mock 邮件 + mock embedding，无需任何外部 key。

## Deployment

部署到 Sacurajima（或任意 Ubuntu 22.04+，2 vCPU / 1.9 GB RAM）：

```bash
DEPLOY_HOST=xivlab@your-server \
DEPLOY_PATH=/opt/xivlab \
HEALTH_URL=https://xivlab.your-domain \
./deploy/deploy.sh
```

部署脚本会：

1. `rsync` 源码到 `/opt/xivlab`（排除 `.venv/`、`data/`、`.git/`）
2. 在服务端运行 `uv sync --frozen`
3. 跑 `alembic upgrade head`
4. `systemctl restart xivlab`
5. 通过 `scripts/check_health.py` 调用 `/health` 验证

systemd unit 与 nginx 模板见 [`deploy/`](./deploy/)。`MemoryMax=500M` 兜底符合内存预算。

创建第一个 admin：

```bash
uv run python scripts/create_admin.py
```

## Architecture

参见 [设计文档](docs/superpowers/specs/2026-05-04-xivlab-design.md)
和 [实施计划](docs/superpowers/plans/2026-05-04-xivlab-implementation.md)。

简言之：单进程 FastAPI + APScheduler in-process 负责 cron；服务器端渲染（Jinja2 + HTMX）；SQLite + sqlite-vec 既存元数据也存语义向量。

## Changelog

详见 [CHANGELOG.md](CHANGELOG.md)。
