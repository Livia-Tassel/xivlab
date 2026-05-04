# xivLab — 设计文档（MVP v1）

**日期**: 2026-05-04
**状态**: 待评审
**目标部署**: Sacurajima (43.135.182.151), Ubuntu 24.04, 2 vCPU / 1.9GB RAM

---

## 1. 概述

### 1.1 一句话定位

**xivLab** 是面向科研人员的开源 AI 工具站，由两个互补模块组成：

- **arXiv 早报**：个性化论文订阅推送服务（自用为主，留商业化接口）
- **PromptHub**：科研场景 AI 提示词的开源社区（社区驱动，始终免费）

### 1.2 解决的问题

科研人员每天面对：

1. arXiv 上千篇新论文，没人看得过来；通用 RSS 工具不会按你的研究方向智能筛选
2. ChatGPT/Claude 等工具在科研场景的 prompt 调教耗时（润色、rebuttal、写 cover letter、画图…），且大家都在**孤军奋战**

xivLab 用一个站点同时解决：

- 模块 A 帮你筛 + 推送你关心的论文
- 模块 C 让科研人员共享调好的 prompt，互相省时间

### 1.3 双模块互导

- 来 PromptHub 找 prompt 的人 → 看到 arXiv 早报入口 → 注册订阅
- 来订阅 arXiv 早报的人 → 看到 PromptHub → 浏览/上传

用户画像统一，账户系统复用。

### 1.4 商业化路径（v2，MVP 阶段不实施但留接口）

- 模块 A：每用户最多 2 个免费 task；超额需购买 credits（freemium）
- 模块 C：始终完全免费，作为流量入口
- 收入路径：Stripe Checkout → 增加 credits → 解锁更多 task slot

### 1.5 资源约束

- **内存预算 < 500MB**（其他进程已占用 ~1.2GB，可用 ~820MB）
- **不依赖 sub2api**（额度紧张），所有 LLM 相关调用走外部 API（用户自带或站点小钱包）

---

## 2. 架构

### 2.1 模块拆分

```
                    [xivLab 综合站]
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
    [模块 A]          [模块 C]           [平台层]
    arXiv 早报         PromptHub         用户/认证/
    (订阅服务)         (社区开源)         Credit/API
```

每个模块在 FastAPI 里是独立的 router，共享平台层（auth, db, email, scheduler）。

### 2.2 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python 3.12 + FastAPI | AI/ML 生态最强、vibe coding 顺、内存表现良好 |
| ORM | SQLAlchemy 2.0 (async) | FastAPI 标配 |
| 数据校验 | Pydantic v2 | FastAPI 自带 |
| 数据库 | SQLite + sqlite-vec | 单文件零运维 + 向量插件支撑语义筛选 |
| Migration | Alembic | SQLAlchemy 标配 |
| 模板 | Jinja2 | FastAPI 标配 |
| 前端 | HTMX + Tailwind (CDN) + Alpine.js | 无 build 步骤、低内存、AI 写得顺 |
| 任务调度 | APScheduler (in-process) | 单进程内嵌，省一个进程 |
| 邮件 | Resend API | 免费额度够 MVP |
| Embedding | OpenAI `text-embedding-3-small` (默认) | $0.02/1M tokens；可换智谱/SiliconFlow |
| 认证 | passlib + 自管 session cookie | 简单可控 |
| 包管理 | uv | 比 pip/poetry 都快 |
| 日志 | structlog (JSON) | systemd journal 可读 |
| 部署 | systemd + nginx + certbot | 复用 Sacurajima 现有 nginx |
| 测试 | pytest + httpx + factory_boy | Python 测试标配 |

### 2.3 架构原则

1. **MVP 优先 + 商业化预留**：MVP 不实施 Stripe / credits，但 schema 表 + 配额 check 接口已经在；v2 切换无需重构
2. **零 sub2api 调用**：MVP 完全不用 sub2api。语义 embedding 用 OpenAI 小模型（极便宜）。LLM 论文摘要延后到 v1.1
3. **服务端渲染优先**：避免 SPA 的内存负担和构建复杂度
4. **API-first**：所有功能先有 REST endpoint，前端再消费。便于后续接 MCP / 公开 API
5. **可观测性从 day 1**：cron_runs 表 + 结构化日志，运维问题能复盘

---

## 3. 模块 A · arXiv 早报

### 3.1 任务模型 (Task)

每用户最多 2 个 task（MVP），每个 task 是一个**每日订阅源**。

```yaml
Task:
  id: int (PK)
  user_id: int (FK users)
  name: str                          # "LLM Agent 跟进"
  arxiv_categories: list[str]        # ["cs.AI", "cs.LG", "cs.CL"]
  keywords: list[str] | None         # ["LLM agent", "tool use", "RAG"]，可选
  min_keyword_match: int = 1
  interest_description: str | None   # 自由文本，会被 embed
  max_papers_per_day: int = 10
  delivery_time: str = "08:00"       # HH:MM, 用户 TZ
  delivery_channels: list[str]       # ["email", "rss"]
  rss_token: str                     # 自动生成 secret，URL 鉴权用
  enabled: bool = True
  created_at, updated_at: datetime
```

**字段语义关系**：

- 只填 `keywords` → 纯关键词筛选
- 只填 `interest_description` → 纯语义筛选
- 都填 → keywords 预筛 + 语义重排（推荐用法）
- 都不填 → 按 category 全推（不推荐但允许）

### 3.2 筛选流程

```
for each enabled task:
  Stage 1 [category 预筛]: papers WHERE primary_category ∈ task.arxiv_categories
  Stage 2 [keyword 命中]: 标题+摘要 lowercase 子串匹配；命中数 ≥ min_keyword_match
  Stage 3 [语义重排]:    若 interest_description 非空：
                          cosine_similarity(paper.embedding, task.embedding) desc
  Stage 4 [取 top]:      max_papers_per_day
  Stage 5 [输出]:        arXiv 原始 abstract（前 4 句截断），不调 LLM
```

每篇 paper 在入库时 embed 一次（OpenAI text-embedding-3-small），存 sqlite-vec。
每个 task 的 description 在创建/更新时 embed 一次，缓存。

### 3.3 数据流（每日 cron）

```
[Cron 02:00 UTC] arXiv 抓取
  ├─ 调 arxiv API 拉过去 24h cs.* 类别新论文
  ├─ upsert 到 papers 表
  ├─ 对新增的每篇 paper 调 embedding API
  └─ 写 paper_vectors (sqlite-vec)

[Cron 用户 delivery_time] 推送
  ├─ for task in user.enabled_tasks:
  │    Stage 1-5 筛选 → top N papers
  │    渲染 email HTML/plain → 发送 (Resend API)
  │    更新 deliveries 表
  └─ 同时为 task 重新生成 RSS feed XML（缓存到磁盘）
```

### 3.4 RSS Feed

URL: `GET /rss/{user_id}/{task_id}/feed.xml?token={rss_token}`

- token 在 task 创建时生成，可在 dashboard 查看 + 重置
- feed 内容：最近 30 天命中本任务的论文（Atom 1.0）
- 每天定时刷新文件缓存，访问时直接 serve

### 3.5 Schema

```sql
CREATE TABLE papers (
  id TEXT PRIMARY KEY,                  -- arxiv id (e.g. "2401.12345")
  title TEXT NOT NULL,
  abstract TEXT NOT NULL,
  authors JSON,                          -- list of strings
  primary_category TEXT,
  all_categories JSON,                   -- list
  published_at DATETIME,
  pdf_url TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_papers_published ON papers(published_at);
CREATE INDEX idx_papers_primary_cat ON papers(primary_category);

-- sqlite-vec virtual table
CREATE VIRTUAL TABLE paper_vectors USING vec0(
  paper_id TEXT PRIMARY KEY,
  embedding FLOAT[1536]                  -- text-embedding-3-small dim
);

CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  arxiv_categories JSON NOT NULL,        -- list
  keywords JSON,                          -- list (nullable)
  min_keyword_match INTEGER DEFAULT 1,
  interest_description TEXT,              -- nullable
  max_papers_per_day INTEGER DEFAULT 10,
  delivery_time TEXT DEFAULT '08:00',
  delivery_channels JSON DEFAULT '["email"]',
  rss_token TEXT NOT NULL UNIQUE,
  enabled BOOLEAN DEFAULT TRUE,
  created_at, updated_at DATETIME
);

CREATE TABLE task_embeddings (
  task_id INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
  embedding BLOB NOT NULL,               -- 1536 floats
  source_text TEXT NOT NULL,             -- 用于检测是否需要重 embed
  embedded_at DATETIME
);

CREATE TABLE deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(id),
  task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
  paper_id TEXT REFERENCES papers(id),
  delivered_at DATETIME,
  channel TEXT,                          -- 'email' / 'rss'
  opened_at DATETIME NULL,
  clicked_at DATETIME NULL
);
CREATE UNIQUE INDEX idx_deliveries_dedup ON deliveries(task_id, paper_id, channel);
```

### 3.6 LLM 摘要 (v1.1，不在 MVP)

待 sub2api 配额情况清楚后开启：

- 摘要按论文缓存（跨用户复用）
- 估算：30~80 篇/天 × 600 in / 200 out tokens

---

## 4. 模块 C · PromptHub

### 4.1 数据模型

```yaml
Prompt:
  id: int (PK)
  slug: str                          # auto from title, URL: /p/reviewer-2-simulator-{id}
  title: str                          # < 100 chars
  description: str                    # < 300 chars
  body: str                           # markdown, < 5000 chars
  category_id: int (FK)
  tags: list[str]                     # 自由
  variables: list[{name, default}] | None   # prompt 模板变量
  example_input, example_output: str | None
  author_user_id: int (FK)
  language: 'zh' | 'en'
  upvotes, copies, views: int
  status: 'pending' | 'published' | 'flagged'
  forked_from_id: int | None         # v2 用
  created_at, updated_at: datetime
```

### 4.2 分类（9 个一级分类）

| slug | 显示名 | 适用场景 |
|---|---|---|
| paper-writing | 论文写作 | 润色、改写、cover letter、rebuttal |
| paper-reading | 论文阅读 | 摘要、批判、问答 |
| code | 代码 | 解释、生成、调试、审计 |
| data-analysis | 数据分析 | matplotlib、pandas、可视化 |
| experiment-design | 实验设计 | hyperparameter、ablation |
| academic-english | 学术英语 | 润色、翻译 |
| literature-review | 文献调研 | 综述、相关工作 |
| admin | 行政事务 | 推荐信、求职信、邮件 |
| misc | 杂项 | - |

每分类下用户自由打 tag（不预设二级分类，避免规划包袱）。

### 4.3 热度排序

- **MVP**: 按 `upvotes desc`
  - 主页：每分类 top 5 卡片 + "本周新增" 栏
  - 分类页：top 20，可切换 "热门 / 最新"
- **v1.1**: HN-style 时间衰减

```
score = (upvotes - 1) / pow(hours_since_post + 2, 1.8)
```

### 4.4 防垃圾（UGC 关键）

**MVP**:

- 邮箱已验证才能上传
- 单用户每天最多上传 5 个 prompt
- Title < 100 / body < 5000 字数硬限制
- 后台手动审核：管理员（你）登录 `/admin/queue` 看新 pending → 通过/拒绝
- 通过后 → published；拒绝 → 删除并记 reason

**v2**:

- 关键词黑名单自动审核
- 用户举报 + 累计阈值自动隐藏

### 4.5 创作流程

```
/prompts/new (登录态)
  └─ 表单: 标题 / 简介 / 分类（下拉）/ 内容（monaco editor + markdown）/
           tags（多选/自由）/ 示例 IO（可选）/ 语言
  └─ 提交 → status='pending'
  └─ 管理员审核 → 'published' or 拒绝
  └─ 上传者 dashboard 可见状态
```

### 4.6 互动

| 动作 | 鉴权 | 反作弊 |
|---|---|---|
| 点赞 | 必须登录 | 用户对单 prompt 唯一 vote 记录（PK 复合键） |
| 复制 | 任何人 | (user_id 或 IP) + 30s 防刷窗口 |
| 浏览 | 任何人 | UA 过滤 + IP 30s 内只算一次 |

### 4.7 Schema

```sql
CREATE TABLE prompt_categories (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  icon TEXT,
  sort_order INTEGER
);

CREATE TABLE prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  body TEXT NOT NULL,
  category_id INTEGER NOT NULL REFERENCES prompt_categories(id),
  tags JSON,                            -- list
  variables JSON,
  example_input TEXT,
  example_output TEXT,
  author_user_id INTEGER NOT NULL REFERENCES users(id),
  language TEXT NOT NULL,
  upvotes INTEGER DEFAULT 0,
  copies INTEGER DEFAULT 0,
  views INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending',         -- 'pending' / 'published' / 'flagged'
  forked_from_id INTEGER REFERENCES prompts(id),
  created_at, updated_at DATETIME
);
CREATE INDEX idx_prompts_cat_status ON prompts(category_id, status);
CREATE INDEX idx_prompts_score ON prompts(upvotes DESC);

CREATE TABLE prompt_votes (
  user_id INTEGER NOT NULL REFERENCES users(id),
  prompt_id INTEGER NOT NULL REFERENCES prompts(id),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, prompt_id)
);

CREATE TABLE prompt_copy_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_id INTEGER NOT NULL REFERENCES prompts(id),
  user_or_ip TEXT NOT NULL,             -- "u:123" or "i:1.2.3.4"
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_copy_dedup ON prompt_copy_events(prompt_id, user_or_ip, created_at);
```

### 4.8 v2 预留

| Feature | 设计预留方式 |
|---|---|
| Fork | `forked_from_id` 字段已建 |
| 版本管理 | 设计 `prompts_history` 表，MVP 不写历史 |
| 在线运行 | 详情页留 "Run" 按钮位置；变量字段已设计成可填表单 |
| 评论 | 设计 `prompt_comments` 表 |

---

## 5. 平台层

### 5.1 用户认证

- **方式**: Email + password + 邮箱验证
- **密码哈希**: passlib[bcrypt]
- **Session**: server-side `sessions` 表 + HttpOnly cookie，30 天滑动续期
- **未验证邮箱用户**: 不能创建 task / 上传 prompt / 点赞，仅可浏览
- **密码重置**: 标准 token + 48h 有效链接
- **v1.1**: + GitHub OAuth

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  email_verified BOOLEAN DEFAULT FALSE,
  display_name TEXT,
  tz TEXT DEFAULT 'Asia/Shanghai',
  is_admin BOOLEAN DEFAULT FALSE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,                  -- random 256-bit
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at DATETIME NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME,
  user_agent TEXT,
  ip TEXT
);

CREATE TABLE email_verification_tokens (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at DATETIME NOT NULL,
  used_at DATETIME
);

CREATE TABLE password_reset_tokens (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at DATETIME NOT NULL,
  used_at DATETIME
);
```

### 5.2 商业化预留（MVP 建表不启用）

```sql
CREATE TABLE user_credits (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  balance INTEGER DEFAULT 0,
  updated_at DATETIME
);

CREATE TABLE credit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  amount INTEGER NOT NULL,              -- + or -
  reason TEXT NOT NULL,                 -- 'topup', 'task_extra_slot', etc.
  ref_type TEXT,                         -- 'stripe_payment', 'admin_grant', etc.
  ref_id TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_quotas (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  max_tasks INTEGER DEFAULT 2,
  last_recalc DATETIME
);
```

**配额检查接口（必须经过）**:

```python
def can_add_task(user_id: int) -> tuple[bool, str]:
    quota = get_or_create_quota(user_id)
    current = count_user_tasks(user_id)
    if current < quota.max_tasks:
        return True, ""
    return False, f"Already at limit ({quota.max_tasks}). Buy credits to extend."
```

**Stripe 挂载点（写在文档，不实施）**:

- `POST /api/v1/billing/checkout` → 创建 Stripe Checkout Session
- `POST /api/v1/webhooks/stripe` → 收事件 → 写 credit_events 增加 balance + 增加 max_tasks

### 5.3 REST API 总览

```
/api/v1
  /auth
    POST /register          {email, password, display_name}
    POST /login             {email, password}
    POST /logout
    POST /verify-email/{token}
    POST /forgot-password   {email}
    POST /reset-password    {token, new_password}
  /me
    GET, PATCH
  /tasks
    GET                     list user's tasks
    POST                    create (passes quota check)
    GET    /{id}
    PATCH  /{id}
    DELETE /{id}
    POST   /{id}/regenerate-rss-token
  /prompts
    GET                     list (?category, ?tag, ?sort, ?lang, ?q)
    POST                    create (status=pending)
    GET    /{slug-id}
    PATCH  /{id}            (作者本人或 admin)
    DELETE /{id}            (作者本人或 admin)
    POST   /{id}/vote
    POST   /{id}/copy-track
    POST   /{id}/view-track
  /categories
    GET
  /admin                    (require is_admin)
    GET  /pending-prompts
    POST /prompts/{id}/approve
    POST /prompts/{id}/reject  {reason}

# 不在 /api 下
/rss/{user_id}/{task_id}/feed.xml?token=<...>
/health
```

### 5.4 前端页面

```
/                       # 主页（PromptHub 入口 + arXiv 早报介绍）
/c/{slug}               # 分类页
/p/{slug}-{id}          # prompt 详情
/prompts/new            # 创建 prompt
/login, /register       # 认证
/verify-email/{token}   # 邮箱激活
/forgot-password
/reset-password/{token}
/dashboard              # 用户工作台（task 列表 + RSS URL）
/dashboard/tasks/new
/dashboard/tasks/{id}
/admin/queue            # 审核队列
/health                 # 健康检查
```

### 5.5 项目结构

```
xivlab/
├─ app/
│  ├─ main.py              # FastAPI app + lifespan + middleware
│  ├─ config.py            # Pydantic Settings
│  ├─ db.py                # engine, session
│  ├─ scheduler.py         # APScheduler 定义
│  ├─ models/              # SQLAlchemy ORM
│  ├─ schemas/             # Pydantic
│  ├─ routers/
│  │   ├─ auth.py
│  │   ├─ tasks.py        (Module A REST)
│  │   ├─ prompts.py      (Module C REST)
│  │   ├─ categories.py
│  │   ├─ admin.py
│  │   ├─ rss.py
│  │   └─ pages.py        (服务端渲染页面)
│  ├─ services/
│  │   ├─ arxiv_fetcher.py
│  │   ├─ embedding.py
│  │   ├─ email.py        (Resend wrapper)
│  │   ├─ feed_renderer.py (RSS XML)
│  │   ├─ digest.py        (筛选 + 推送 pipeline)
│  │   └─ quota.py
│  └─ deps.py             # FastAPI dependencies (current_user, etc.)
├─ alembic/                 # migrations
├─ templates/               # Jinja2
├─ static/                  # CSS / JS / images
├─ tests/
├─ scripts/                 # init admin, manual cron, etc.
├─ docs/superpowers/specs/  # 设计文档
├─ pyproject.toml           # uv
├─ .env.example
└─ README.md
```

---

## 6. 部署 & 运维

### 6.1 环境

| 项 | 值 |
|---|---|
| 服务器 | Sacurajima (43.135.182.151) |
| OS | Ubuntu 24.04 |
| 项目路径 | `/opt/xivlab/` |
| Python | 3.12 (uv 管理) |
| 数据 | `/opt/xivlab/data/app.db` (SQLite WAL) |
| 备份 | `/opt/xivlab/data/backups/app-YYYY-MM-DD.db` (保留 14 天) |
| 监听 | 127.0.0.1:8001 |

### 6.2 systemd unit

```ini
# /etc/systemd/system/xivlab.service
[Unit]
Description=xivLab - research AI tools
After=network.target

[Service]
Type=simple
User=xivlab
WorkingDirectory=/opt/xivlab
EnvironmentFile=/opt/xivlab/.env
ExecStart=/opt/xivlab/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
Restart=on-failure
RestartSec=5
MemoryMax=500M
MemoryHigh=400M

[Install]
WantedBy=multi-user.target
```

### 6.3 nginx

```nginx
# /etc/nginx/sites-enabled/xivlab.conf
server {
    listen 80;
    server_name xivlab.<your-domain>;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name xivlab.<your-domain>;

    ssl_certificate     /etc/letsencrypt/live/xivlab.<your-domain>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/xivlab.<your-domain>/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/xivlab/static/;
        expires 7d;
    }
}
```

### 6.4 定时任务（APScheduler in-process）

| 任务 | 频率 | 描述 |
|---|---|---|
| `fetch_arxiv` | 每天 02:00 UTC | 拉 arXiv 新论文，embed |
| `send_digests` | 每分钟 tick | 检查所有 user.delivery_time 命中本分钟 → 推送 |
| `refresh_rss` | 每天 03:00 UTC | 刷新所有 task 的 RSS 缓存文件 |
| `db_backup` | 每天 04:00 UTC | sqlite3 .backup → 保留最近 14 天 |
| `cleanup_sessions` | 每天 04:30 UTC | 删过期 sessions / 已用 tokens |

每个任务执行写入 `cron_runs(id, name, started_at, ended_at, status, error)`，便于排查。

### 6.5 .env 配置

```
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
SECRET_KEY=<random-32bytes-hex>

# Email
RESEND_API_KEY=...
RESEND_FROM_EMAIL=noreply@<your-domain>
ADMIN_EMAILS=<your-email>

# Embedding
EMBEDDING_PROVIDER=openai          # openai | zhipu | siliconflow
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=...
# ZHIPU_API_KEY=...
# SILICONFLOW_API_KEY=...

# arXiv
ARXIV_CATEGORIES=cs.AI,cs.LG,cs.CL,cs.CV,cs.CR,cs.DB,cs.DC,cs.DS,cs.HC,cs.IR,stat.ML

# App
APP_BASE_URL=https://xivlab.<your-domain>
APP_ENV=production
```

### 6.6 监控与日志

| 项 | 实现 |
|---|---|
| 应用日志 | `structlog` JSON → systemd journal (`journalctl -u xivlab`) |
| Cron 状态 | `cron_runs` 表 + `/admin` 页面看最近运行 |
| 错误告警 | cron 失败 → 自动给 ADMIN_EMAILS 发邮件 |
| Health check | `GET /health` 返回 DB ping + 最近 cron 状态 |
| v1.1 | + Sentry / Plausible |

### 6.7 内存预算复核

| 进程组件 | 估占用 |
|---|---|
| uvicorn + FastAPI 空跑 | 80MB |
| sqlalchemy + async pool | +30MB |
| sqlite-vec 工作集（10K 向量加载） | +30MB |
| jinja2 templates 缓存 | +10MB |
| APScheduler + arxiv 抓取临时缓冲 | +20-50MB |
| LLM/embedding HTTP 客户端 | +10MB |
| **典型 idle** | **~150MB** |
| **早报抓取/推送峰值** | **~250-350MB** |

**预算 < 500MB 完全打得住**，systemd `MemoryMax=500M` 兜底。

### 6.8 部署清单

1. 在 Sacurajima 创建系统 user `xivlab` + `/opt/xivlab/`
2. 上传/clone repo + `uv venv` + `uv sync`
3. 配置 `/opt/xivlab/.env`
4. `alembic upgrade head` 初始化 schema + seed 9 个 prompt categories
5. 写 systemd unit + 启用
6. 写 nginx conf + reload
7. certbot 申请 SSL
8. 创建 admin 账号（命令行脚本 `scripts/create_admin.py`）
9. 域名指向 Sacurajima IP
10. Smoke test：注册→邮箱激活→创建 task→查看 RSS→上传 prompt→管理员审核

---

## 7. 测试策略

### 7.1 框架

`pytest + pytest-asyncio + httpx.AsyncClient + factory_boy`

### 7.2 优先级

**P0（必测）**:

- 认证流：register / login / logout / email verify / password reset
- Task CRUD + 配额检查（最多 2 个）
- 防垃圾：每天 5 个 prompt 上限、字数限制
- RSS feed 生成 + token 鉴权
- 数据库 migration

**P1（应测）**:

- arXiv pipeline 单元测试（mock arxiv api）
- Embedding 调用（mock OpenAI）
- 邮件渲染（不实际发送，验证 HTML 正确）
- 热度排序逻辑
- Admin 审核流程

**P2（最好测）**:

- 端到端注册→订阅→收推送 flow（mock 全外部依赖）
- 跨模块互导（dashboard 能看到 prompts 也能看到 tasks）

### 7.3 Mock 策略

- arXiv API: fixture 文件存样本响应
- OpenAI Embedding: mock 返回 1536-dim 确定性向量（基于 seed）
- Resend: 不实际发送，记 `(to, subject, body)` 到内存

### 7.4 CI

GitHub Actions：

- PR 必跑 pytest
- main 推送后跑 smoke test
- 暂不部署自动化（v2 加）

---

## 8. MVP vs v2 边界

### 8.1 MVP（必交付）

✅ 用户系统：register / login / logout / email verify / password reset
✅ Module A：Task CRUD（每用户上限 2）/ 关键词+语义筛选 / Email + RSS 推送 / arxiv 抓取 + embedding cron
✅ Module C：Prompt CRUD / 9 分类 / 点赞 / 复制计数 / 浏览量 / 主页+分类页+详情页 / 管理员审核队列
✅ 平台：REST API + OpenAPI 文档 / 健康检查 / 数据备份 cron / 结构化日志
✅ 商业化预留：credit/quota schema 表已建 + can_add_task 接口 + Stripe 文档

### 8.2 v1.1（公开 launch 后）

- LLM 论文摘要（按论文缓存）
- HN-style 热度时间衰减
- GitHub OAuth
- Sentry / Plausible

### 8.3 v2（商业化）

- Stripe 集成 + Credit 购买
- Task 上限超额扣 credit
- Telegram 推送渠道
- Prompt Fork
- Prompt 在线运行（用户自带 key）
- Prompt 评论
- Prompt 版本管理
- 关键词自动审核

---

## 9. 开放问题 / 已知风险

### 9.1 待确认

1. **域名**：xivLab 的子域名/独立域名待用户决定
2. **管理员邮箱**：admin 账号用哪个邮箱（接收审核 / 错误告警）
3. **Resend 账号**：用户是否已注册？发件域名 DNS 配置（DKIM/SPF）
4. **Embedding provider**：MVP 默认 OpenAI；如果国内调不通，切智谱/SiliconFlow
5. **Sub2api 配额**：实际剩余多少？决定 v1.1 LLM 摘要何时开

### 9.2 风险

| 风险 | 缓解 |
|---|---|
| arXiv API 限速（3s/req） | 全局令牌桶 + 重试退避 |
| 单 SQLite 写并发 | WAL mode + connection pool 严格限大小 |
| 内存峰值打满 | systemd `MemoryMax=500M` 兜底；监控 OOM |
| 邮件发送失败 | Resend 重试 + 失败告警邮件给 admin |
| 垃圾 prompt 涌入 | MVP 全人工审核；上限 5/天/人 |
| OpenAI 在国内被墙 | 通过国内代理；或换智谱/SiliconFlow embedding |
| Cron 漏跑 | `cron_runs` 表 + 启动时检查最近 24h 必跑任务是否执行 |

---

## 10. 命名 / 品牌

- **项目名**: xivLab
- **GitHub repo**: `xivlab`
- **域名**: 待定（建议 xivlab.dev / xivlab.app / xivlab.ai）
- **Tagline 候选**:
  - "为科研人定制的 AI 工具站"
  - "arXiv 早报 + 科研 prompt 社区"
- **Logo**: 后续设计（emoji 占位：🧪）
