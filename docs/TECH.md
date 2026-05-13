# knowwind-wx 技术实现文档

---

## 定位

knowwind-wx 是 KnowWind 的微信数据源插件。它是一个后台服务，没有独立的用户界面，必须配合 KnowWind 核心平台使用。

**依赖关系**：必须先安装 KnowWind，再安装 knowwind-wx。

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后台服务 | Python 3.10+ | 常驻进程，监听 KnowWind 指令 |
| 配置界面 | Vue 3（CDN） | 注册进 KnowWind 导航，插件自己渲染 |
| 数据库 | SQLite | 插件私有，存策略、群配置、历史反馈 |
| 消息采集 | wechat-decrypt HTTP API | 本机微信消息读取 |
| LLM 提取 | Claude Code CLI / Anthropic SDK | 候选消息精提取 |
| 与 KnowWind 通信 | REST API（HTTP） | 推送 insights、注册插件、接收指令 |

---

## 目录结构

```
knowwind-wx/
├── config.example.sh          # 配置模板
├── config.sh                  # 用户配置（不提交 Git）
├── AGENTS.md                  # AI 操作规则手册
├── README.md                  # 安装和使用说明
├── docs/
│   └── TECH.md                # 本文件
├── data/
│   └── wx_still.db            # 插件私有 SQLite 数据库
├── server/
│   └── main.py                # 后台服务入口（FastAPI）
├── ui/
│   └── index.html             # 配置界面（Vue 3 CDN，注册进 KnowWind）
└── scripts/
    ├── export-wechat-groups.sh  # 调用 wechat-decrypt，拉取增量消息
    ├── extract-insights.py      # 规则粗过滤 + LLM 精提取
    └── push-insights.py         # 推送 insights 给 KnowWind
```

---

## 数据库设计

数据库文件：`data/wx_still.db`

### groups 表（群配置）

```sql
CREATE TABLE groups (
    id TEXT PRIMARY KEY,           -- 群唯一标识（来自 wechat-decrypt）
    name TEXT NOT NULL,            -- 群名称
    enabled INTEGER DEFAULT 1,     -- 是否启用采集（1=是，0=否）
    strategy_label TEXT,           -- 策略标签（技术问答群/资讯分享群/通用群）
    strategy_extra TEXT,           -- 用户自定义补充（自然语言）
    strategy_feedback TEXT,        -- 历史反馈（点评沉淀，自动追加）
    last_fetched_at INTEGER DEFAULT 0,  -- 上次采集时刻（Unix 时间戳，增量采集用）
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
```

### fetch_logs 表（采集日志）

```sql
CREATE TABLE fetch_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT NOT NULL,        -- 采集的群
    fetched_at INTEGER NOT NULL,   -- 采集时刻
    message_count INTEGER,         -- 拉取的原始消息数
    candidate_count INTEGER,       -- 规则过滤后候选数
    insight_count INTEGER,         -- LLM 提取后 insight 数
    pushed_count INTEGER,          -- 成功推送给 KnowWind 的数
    status TEXT,                   -- success / failed
    error TEXT                     -- 失败原因
);
```

---

## 后台服务

### 入口：`server/main.py`

基于 FastAPI，常驻后台运行，监听 `localhost:8001`（KnowWind 默认 `8000`，插件默认 `8001`）。提供以下接口供 KnowWind 调用：

```
GET  /health                    # 健康检查，KnowWind 用来确认插件在线
GET  /info                      # 插件信息（名称、版本、UI 入口路径）
GET  /groups                    # 返回所有群列表（含策略配置）
POST /groups/{id}/strategy      # 更新某个群的策略
POST /collect                   # 触发采集（KnowWind 界面点「采集」时调用）
GET  /collect/status            # 查询当前采集进度
```

### 插件注册

服务启动时，自动向 KnowWind 注册自己：

```
POST {KNOWWIND_URL}/api/plugins/register
{
    "name": "wechat",
    "display_name": "微信",
    "version": "1.0.0",
    "url": "http://localhost:8001",
    "ui_path": "/ui/index.html"
}
```

KnowWind 收到注册后，在导航里自动出现「微信」入口，点击加载 `ui_path` 指向的页面。

### 启动方式

安装时按平台注册开机自启，用户无感知：

macOS（launchd）：
```xml
<!-- ~/Library/LaunchAgents/com.knowwind.knowwind-wx.plist -->
<key>ProgramArguments</key>
<array>
    <string>python3</string>
    <string>/path/to/knowwind-wx/server/main.py</string>
</array>
<key>RunAtLoad</key>
<true/>
```

Windows（任务计划程序）：
```
schtasks /create /tn "knowwind-wx" /tr "python3 /path/to/knowwind-wx/server/main.py" /sc onlogon
```

Linux（systemd）：
```ini
# ~/.config/systemd/user/knowwind-wx.service
[Service]
ExecStart=python3 /path/to/knowwind-wx/server/main.py
Restart=on-failure

[Install]
WantedBy=default.target
```

---

## 配置界面

### `ui/index.html`

Vue 3 CDN 单页面，注册进 KnowWind 导航后由 KnowWind 的 iframe 加载。

页面功能：
1. **群列表**：从 `/groups` 拉取，显示所有微信群，可勾选启用/停用
2. **策略配置**：
   - 选择策略标签（技术问答群 / 资讯分享群 / 通用群）
   - 自然语言补充输入框（placeholder 引导用户写过滤规则、关注点等）
   - 历史反馈展示（只读，由点评自动沉淀）
3. **采集按钮**：点击调用 KnowWind 的采集触发接口
4. **采集状态**：轮询 `/collect/status`，显示当前进度

---

## 数据流详解

### 第一步：拉取消息（`export-wechat-groups.sh`）

```bash
# 计算 last_fetched_at（从数据库读取）
# 调用 wechat-decrypt API
curl "{WECHAT_DECRYPT_URL}/api/history?since={last_fetched_at}&limit=2000"

# 按 GROUP_KEYWORDS 过滤目标群
# 写入临时文件 /private/tmp/wx_messages_YYYY-MM-DD.json
# 更新数据库中的 last_fetched_at
```

wechat-decrypt 消息字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT | 消息唯一 ID |
| chat | TEXT | 群名称 |
| sender | TEXT | 发送者（提取后丢弃，不推送给 KnowWind） |
| type | TEXT | text / image / system / emoji / file / link |
| content | TEXT | 消息内容 |
| timestamp | INTEGER | 消息时间戳 |

### 第二步：规则粗过滤（`extract-insights.py` 第一阶段）

丢弃条件（任意一条命中即丢弃）：
- `type` 为 `system` 或 `emoji`
- 文本长度 < `MIN_QUESTION_LENGTH`（默认 8）
- 内容含过滤关键词：`拍了拍`、`撤回了`、`加入了群聊`、`邀请`、`修改群名`

进入候选池条件：
- `type` 为 `text`
- 命中问题关键词（见 AGENTS.md）

图片、文件、链接类消息：不作为候选，但保留在上下文中供 LLM 参考。

### 第三步：LLM 精提取（`extract-insights.py` 第二阶段）

将候选消息连同上下文批量发给 LLM，一次调用返回所有 insights。

提示词构成：
```
[策略标签模板内容]
[用户自定义补充]
[历史反馈]

以下是微信群消息，请按上述策略提取有价值的内容：
[候选消息列表（含上下文）]
```

LLM 输出格式（JSON 数组）：
```json
[
  {
    "type": "qa",
    "title": "怎么在 Claude 里调用自定义工具？",
    "content": "完整问题和答案内容",
    "score": 87,
    "score_reason": "答案完整，有可操作步骤",
    "occurred_at": 1746700800
  }
]
```

LLM 调用方式（按优先级）：
1. `claude` CLI（复用 Claude Code 登录账号）
2. Anthropic Python SDK（需 `ANTHROPIC_API_KEY`）
3. 两者都没有：退化为纯规则提取，跳过 LLM 步骤

### 第四步：推送（`push-insights.py`）

敏感话题过滤后，逐条推送给 KnowWind：

```
POST {KNOWWIND_URL}/api/insights
Authorization: {KNOWWIND_TOKEN}

{
  "source": "wechat",
  "type": "qa",
  "title": "...",
  "content": "...",
  "score": 87,
  "score_reason": "...",
  "occurred_at": 1746700800,
  "extra": {
    "group_name": "AI大航海"
  }
}
```

推送完成后，写入 `fetch_logs` 表记录本次采集结果。

---

## 点评与策略完善

用户在 KnowWind 界面对某条 insight 点评后，KnowWind 调用插件接口：

```
POST /feedback
{
  "group_id": "xxx",
  "insight_id": "yyy",
  "feedback": "这条答案不完整，没有说清楚怎么配置"
}
```

插件收到后：
1. 调用 LLM，将反馈转化为策略规则（一句话）
2. 追加到该群的 `strategy_feedback` 字段
3. 下次采集时，`strategy_feedback` 自动合并进提示词

---

## 安全要求

- `all_keys.json`（wechat-decrypt 密钥文件）：不打印、不上传、不提交 Git
- `config.sh`：已加入 `.gitignore`
- 推送给 KnowWind 的数据：不含发言人、微信 ID、群成员昵称
- `sender` 字段：采集后立即丢弃，不写入任何文件

---

## 将来扩展

| 方向 | 说明 |
|------|------|
| 多模型支持 | 在群策略配置里增加模型选择，不同群可用不同模型 |
| 图片内容提取 | 调用 wechat-decrypt `/img/{filename}` 接口，结合视觉模型提取图片内容 |
| 语音转文字 | wechat-decrypt 支持语音转录，可接入提取流程 |
| 推送地址可配置 | `KNOWWIND_URL` 从 `localhost` 改为 SaaS 域名，插件代码不变 |
