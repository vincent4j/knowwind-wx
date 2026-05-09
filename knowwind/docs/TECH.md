# KnowWind 技术实现文档

---

## 定位

KnowWind 是决策平台的核心，负责：
- 托管插件的配置界面
- 接收插件推送的 insights
- 存储和展示所有数据
- 对外暴露 MCP 接口供外部 AI 调用

插件依赖 KnowWind 运行，KnowWind 不依赖任何特定插件。

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后台服务 | Python 3.10+ / FastAPI | REST API + MCP Server |
| Web UI | Vue 3（CDN） | 主界面 + 插件导航容器 |
| 数据库 | SQLite（当前）/ PostgreSQL（SaaS） | 存储 insights 和插件注册信息 |
| MCP Server | MCP 协议 | 对外暴露数据查询接口 |
| 启动方式 | macOS launchd / Windows 任务计划程序 / Linux systemd | 开机自启，用户无感知 |

---

## 目录结构

```
knowwind/
├── docs/
│   ├── DESIGN.md              # 产品设计文档
│   ├── USER_JOURNEY.md        # 用户旅途
│   └── TECH.md                # 本文件
├── data/
│   └── knowwind.db            # SQLite 数据库
├── server/
│   ├── main.py                # 服务入口
│   ├── api/
│   │   ├── insights.py        # insights CRUD 接口
│   │   ├── plugins.py         # 插件注册和管理接口
│   │   └── feedback.py        # 点评接口
│   ├── mcp/
│   │   └── server.py          # MCP Server
│   └── db/
│       ├── schema.py          # 数据库表定义
│       └── repository.py      # 数据访问层（抽象，将来换 PostgreSQL 只改这里）
└── ui/
    ├── index.html             # 主界面入口
    ├── components/
    │   ├── InsightCard.js     # insight 卡片组件（QA / 链接 / 话题）
    │   ├── PluginNav.js       # 插件导航（Obsidian 风格）
    │   └── FeedbackBar.js     # 底部点评对话框
    └── pages/
        ├── Home.js            # 主列表页
        └── PluginFrame.js     # 插件配置页容器（iframe）
```

---

## 数据库设计

数据库文件：`data/knowwind.db`

数据访问层抽象在 `server/db/repository.py`，将来换 PostgreSQL 只改这一个文件，业务逻辑不动。

### insights 表

```sql
CREATE TABLE insights (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',  -- 本地版固定 'local'，SaaS 版为真实用户 ID
    source TEXT NOT NULL,                   -- 数据源（wechat / twitter / xiaohongshu…）
    type TEXT NOT NULL,                     -- qa / link / topic
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    score INTEGER,                          -- 置信度评分（0-100）
    score_reason TEXT,                      -- 评分理由（一句话）
    occurred_at INTEGER NOT NULL,           -- 内容发生时间（Unix 时间戳）
    created_at INTEGER NOT NULL,            -- 写入时间
    exported INTEGER DEFAULT 0,             -- 是否已导出（0/1）
    extra TEXT                              -- 插件自定义扩展字段（JSON 字符串）
);

CREATE INDEX idx_insights_source ON insights(source);
CREATE INDEX idx_insights_type ON insights(type);
CREATE INDEX idx_insights_occurred_at ON insights(occurred_at);
CREATE INDEX idx_insights_score ON insights(score);
```

### plugins 表（已注册的插件）

```sql
CREATE TABLE plugins (
    name TEXT PRIMARY KEY,          -- 插件唯一标识（如 wechat）
    display_name TEXT NOT NULL,     -- 显示名称（如 微信）
    version TEXT,
    url TEXT NOT NULL,              -- 插件后台服务地址（如 http://localhost:8001）
    ui_path TEXT NOT NULL,          -- 插件配置界面路径（如 /ui/index.html）
    status TEXT DEFAULT 'online',   -- online / offline
    registered_at INTEGER NOT NULL,
    last_seen_at INTEGER
);
```

### feedback_logs 表（点评记录）

```sql
CREATE TABLE feedback_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insight_id TEXT NOT NULL,       -- 被点评的 insight
    source TEXT NOT NULL,           -- 来源数据源
    scope TEXT NOT NULL,            -- single（单条）/ global（整体）
    content TEXT NOT NULL,          -- 点评内容
    created_at INTEGER NOT NULL
);
```

---

## REST API

### insights 接口

```
POST   /api/insights              # 插件推送 insights（批量）
GET    /api/insights              # 查询 insights（支持过滤、排序、分页）
GET    /api/insights/{id}         # 获取单条 insight
PATCH  /api/insights/{id}         # 更新 insight（如标记已导出）
```

**POST /api/insights 请求体**：

```json
[
  {
    "source": "wechat",
    "type": "qa",
    "title": "怎么在 Claude 里调用自定义工具？",
    "content": "完整内容",
    "score": 87,
    "score_reason": "答案完整，有可操作步骤",
    "occurred_at": 1746700800,
    "extra": { "group_name": "AI大航海" }
  }
]
```

**GET /api/insights 查询参数**：

| 参数 | 说明 |
|------|------|
| source | 按数据源过滤（wechat / twitter…） |
| type | 按类型过滤（qa / link / topic） |
| date | 按日期过滤（YYYY-MM-DD） |
| min_score | 最低评分过滤 |
| q | 全文搜索关键词 |
| sort | 排序（occurred_at_desc / score_desc） |
| page / page_size | 分页 |

### 插件管理接口

```
POST  /api/plugins/register       # 插件启动时注册自己
GET   /api/plugins                # 获取所有已注册插件列表
GET   /api/plugins/{name}/status  # 查询插件在线状态
```

**POST /api/plugins/register 请求体**：

```json
{
  "name": "wechat",
  "display_name": "微信",
  "version": "1.0.0",
  "url": "http://localhost:8001",
  "ui_path": "/ui/index.html"
}
```

### 点评接口

```
POST /api/feedback                # 提交点评（单条或整体）
```

**请求体**：

```json
{
  "insight_id": "xxx",            -- 单条点评时填，整体点评时为 null
  "source": "wechat",             -- 点评针对哪个数据源
  "scope": "single",              -- single / global
  "content": "这条答案不完整"
}
```

KnowWind 收到点评后，转发给对应插件的 `/feedback` 接口，由插件负责更新策略。

收到插件策略更新完成的响应后，KnowWind 向前端推送通知：「策略已更新，是否立刻重跑？」

- 用户选「立刻重跑」：KnowWind 调用插件 `POST /collect`，传入 `rerun=true`，插件用新策略重新提取上次同一批消息，推送新结果覆盖旧结果
- 用户选「下次生效」：本次结果不变，下次采集时新策略自动带入

### 认证

```
Authorization: Bearer {token}
```

当前本地版：token 固定为 `local`，服务端不校验。
将来 SaaS 版：校验真实 token，接口代码不变，只改校验逻辑。

---

## Web UI

### 主界面（`ui/pages/Home.js`）

```
[微信] [Twitter] [小红书] [全部]         排序▼  筛选▼

┌─────────────────────────────────────────────────┐
│ 怎么在 Claude 里调用自定义工具？          87分    │
│ 答案完整，有可操作步骤                           │
│ 2026-05-09 14:23  微信·AI大航海  QA   [点评]    │
└─────────────────────────────────────────────────┘

─────────────────────────────────────────────────
[整体点评：今天的结果怎么样？                    ]
```

- 顶部 tab：从 `/api/plugins` 动态生成，新插件注册后自动出现
- 列表：调用 `/api/insights` 拉取，支持排序和筛选
- 卡片类型：QA / 链接 / 话题，由 `type` 字段决定，AI 提取时自动判断
- 点评按钮：调用 `/api/feedback`，提交后转发给插件
- 底部对话框：整体点评，`scope=global`

### 插件配置页容器（`ui/pages/PluginFrame.js`）

用 iframe 加载插件的 `ui_path`，KnowWind 只提供容器，不感知插件界面内容。

参考 Obsidian 插件设置机制：KnowWind 导航里每个插件对应一个入口，点击加载对应插件的配置页面。

### 首次启动引导

KnowWind 检测到 `plugins` 表为空时，显示引导页：
1. 提示「还没有数据源」
2. 展示可用插件列表（内置，随版本更新）
3. 用户点「安装」，触发 AI Agent 执行安装脚本
4. 安装完成，插件自动注册，导航出现新 tab

---

## MCP Server

文件：`server/mcp/server.py`

暴露以下 tools，供外部 AI（OpenClaw 等）调用：

### 当前

| Tool | 参数 | 说明 |
|------|------|------|
| `list_insights` | source, type, date, min_score, page | 查询 insights |
| `get_insight` | id | 获取单条完整内容 |
| `search_insights` | q, source, type | 全文搜索 |
| `list_sources` | 无 | 查询已注册的数据源 |

### 将来（新增，不改现有接口）

| Tool | 说明 |
|------|------|
| `export_markdown` | 导出为 Markdown 文件 |
| `export_feishu` | 写入飞书文档 |

---

## 启动与部署

### 本地版

安装时按平台注册开机自启，用户无感知：

macOS（launchd）：
```xml
<!-- ~/Library/LaunchAgents/com.knowwind.plist -->
<key>ProgramArguments</key>
<array>
    <string>python3</string>
    <string>/path/to/knowwind/server/main.py</string>
</array>
<key>RunAtLoad</key>
<true/>
```

Windows（任务计划程序）：
```
schtasks /create /tn "KnowWind" /tr "python3 /path/to/knowwind/server/main.py" /sc onlogon
```

Linux（systemd）：
```ini
# ~/.config/systemd/user/knowwind.service
[Service]
ExecStart=python3 /path/to/knowwind/server/main.py
Restart=on-failure

[Install]
WantedBy=default.target
```

服务启动后监听 `localhost:8000`，浏览器访问即可使用。

### 将来（SaaS）

同一套代码，部署到云服务器。新增：
- 用户注册登录系统
- `user_id` 从固定值 `local` 变为真实用户 ID
- SQLite 换 PostgreSQL（只改 `server/db/repository.py`）
- API token 校验开启
- Web 服务器（Nginx 反向代理）

---

## 插件通信协议

KnowWind 与插件之间的通信：

| 方向 | 接口 | 说明 |
|------|------|------|
| 插件 → KnowWind | `POST /api/plugins/register` | 插件启动时注册 |
| 插件 → KnowWind | `POST /api/insights` | 推送清洗后的 insights |
| KnowWind → 插件 | `POST {plugin_url}/collect` | 触发采集 |
| KnowWind → 插件 | `GET {plugin_url}/collect/status` | 查询采集进度 |
| KnowWind → 插件 | `POST {plugin_url}/feedback` | 转发用户点评 |
| KnowWind → 插件 | `GET {plugin_url}/health` | 心跳检测 |

KnowWind 定期对所有已注册插件发送 `/health` 心跳检测，更新 `plugins.status` 字段，界面上显示插件在线/离线状态。

---

## 将来扩展

| 方向 | 说明 |
|------|------|
| 云端数据源 | Twitter、小红书等，KnowWind 直接采集，不需要本地插件 |
| 多用户 | `user_id` 字段已预留，加用户系统即可 |
| 换数据库 | `repository.py` 抽象层，换 PostgreSQL 不改业务逻辑 |
| 语义搜索 | 先 SQLite 拉候选集，再 LLM 判断相关性，不引入向量库 |
| 导出功能 | MCP Server 新增 tool，不改现有接口 |
