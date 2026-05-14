# knowwind-wx 操作规则手册

> 本文件是微信插件的完整规则手册。AI 每次操作前必须读这份文件。

---

## 项目定位

`knowwind-wx` 是 KnowWind 决策平台的微信数据源插件。

职责：从本机微信群采集消息 → 规则粗过滤 → LLM 精提取 → 推送给 KnowWind。

完整架构见 `knowwind/docs/DESIGN.md`。

---

## 配置文件

所有用户相关配置集中在项目根目录的 `.env`。

```bash
cp .env.example .env
# 编辑 .env，至少改以下两项：
#   GROUP_KEYWORDS        目标微信群名称关键词（逗号分隔）
#   WECHAT_DECRYPT_URL    wechat-decrypt 服务地址（默认 http://localhost:5678）
```

可选配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WECHAT_DECRYPT_URL` | `http://localhost:5678` | wechat-decrypt 服务地址 |
| `GROUP_KEYWORDS` | `（空，采集全部群）` | 目标微信群名称关键词（逗号分隔） |
| `KNOWWIND_URL` | `http://localhost:8000` | KnowWind 核心平台地址（推送目标） |
| `KNOWWIND_TOKEN` | `（空）` | KnowWind 鉴权 Token |
| `ANTHROPIC_MODEL` | `claude-opus-4-5` | LLM 精提取使用的模型 |
| `MIN_QUESTION_LENGTH` | `8` | 有效问题的最短字符数 |

---

## 环境依赖

### wechat-decrypt

- GitHub：https://github.com/ylytdeng/wechat-decrypt
- 服务地址由 `.env` 中的 `WECHAT_DECRYPT_URL` 指定（默认 `http://localhost:5678`）
- 支持 Windows、macOS、Linux，不上服务器，不进 Docker
- 微信需在前台运行并已登录
- macOS 上需对 WeChat.app 做 ad-hoc 重签名（一次性，微信升级后重做）：
  ```bash
  sudo codesign --force --deep --sign - /Applications/WeChat.app
  ```
- 每次使用前需手动启动服务：

  macOS：
  ```bash
  cd /path/to/wechat-decrypt
  sudo ./find_all_keys_macos
  python3 main.py
  ```

  Windows / Linux：
  ```bash
  cd /path/to/wechat-decrypt
  python3 main.py
  ```

### Python

- Python 3.10+，依赖见 `requirements.txt`（fastapi, uvicorn, httpx, python-dotenv）

### LLM

- 当前：复用 Claude Code 当前登录账号（通过 `claude` CLI 调用）
- 备选：设置 `ANTHROPIC_API_KEY` 环境变量，使用 Anthropic Python SDK
- 两者都没有：LLM 提取步骤自动跳过，退化为纯规则提取

---

## 工具边界

- 不修改 wechat-decrypt 源码
- 不重新实现微信数据库读取逻辑
- 不采集无关微信群
- 不做自动回复
- 不保存完整聊天原文到项目目录
- 输出 insights 时，不保留发言人、微信 ID、群成员昵称

---

## 数据流

```
wechat-decrypt HTTP API
        ↓
server/main.py (_run_collect)
（按群逐一拉取增量消息）
        ↓
server/insights.py (filter_candidates)
（规则粗过滤：系统消息、表情、短句、黑名单词）
        ↓
server/insights.py (extract_insights)
（LLM 精提取：claude CLI → Anthropic SDK → 规则降级）
        ↓
server/insights.py (push_insights)
（推送给 KnowWind REST API：POST /api/insights）
```

---

## 采集机制

- **增量采集**：数据库记录每群的 `last_fetched_at`（Unix 时间戳），每次只拉取之后的新消息
- **触发方式**：人工触发（KnowWind 界面按钮 → `POST /collect`），不自动定时
- **群过滤**：从 wechat-decrypt 拉取全量消息后，按 `GROUP_KEYWORDS` 过滤目标群

wechat-decrypt API 调用方式：
```
GET {WECHAT_DECRYPT_URL}/api/history?chat={group_name}&since={last_fetched_at}&limit=2000
```

---

## 提取规则

### 第一步：规则粗过滤（`server/insights.py: filter_candidates`）

以下消息直接丢弃：
- 消息类型为 `system`/`系统`（系统消息）
- 消息类型为 `emoji`/`表情`（纯表情）
- 内容命中过滤关键词：`拍了拍`、`撤回了`、`加入了群聊`、`邀请`、`修改群名`

命中以下任意关键词，进入候选池（候选仅限 `text`/`文本`/`链接/文件` 类型且长度 ≥ `MIN_QUESTION_LENGTH`）：
```
请问 问下 问一下 想问 怎么 如何 为什么 为啥
能不能 有没有 可以吗 报错 安装 登录 提交
无法 不显示 不能 失败 错误 问题 #举手 ？ ?
```

### 第二步：LLM 精提取（`server/insights.py: extract_insights`）

输入：候选消息批量 + 策略提示词（标签模板 + 用户补充 + 历史反馈）

降级顺序：`claude` CLI → Anthropic SDK → 规则直接返回（score=50）

输出每条 insight 的结构：
```json
{
  "type": "qa | link | topic",
  "title": "简短标题",
  "content": "完整内容",
  "score": 87,
  "score_reason": "答案完整，有可操作步骤",
  "occurred_at": 1746700800
}
```

### 敏感话题过滤

title + content 命中以下关键词，整条丢弃（不推送给 KnowWind）：
```
科学上网 梯子 翻墙 VPN vpn 代理 上科技
机场 节点 clash Clash shadowsocks v2ray trojan
```

---

## 策略

策略本质是一段提示词，由三部分组成：

| 部分 | 说明 | 可修改 |
|------|------|--------|
| 策略标签 | 预设模板（技术问答群 / 资讯分享群 / 通用群） | 不可修改，要改需删除重建 |
| 自定义补充 | 用户自然语言追加 | 随时可完善 |
| 历史反馈 | 用户点评沉淀的规则，自动追加 | 自动维护 |

策略存储在本地数据库（`data/wx_still.db`），每个群独立配置。

反馈接收后，自动调用 LLM 分析累积反馈，更新 `strategy_label` 和 `strategy_extra`（`POST /feedback` → `derive_strategy_from_feedback`）。

---

## 推送规范

推送目标：`KNOWWIND_URL`（默认 `http://localhost:8000`）

推送接口：`POST /api/insights`

请求头：`Authorization: {KNOWWIND_TOKEN}`（当前本地版不校验，将来 SaaS 版校验）

推送字段：

```json
{
  "source": "wechat",
  "type": "qa",
  "title": "怎么在 Claude 里调用自定义工具？",
  "content": "完整问题和答案内容",
  "score": 87,
  "score_reason": "答案完整，有可操作步骤",
  "occurred_at": 1746700800,
  "extra": {
    "group_name": "AI大航海"
  }
}
```

注意：`extra` 字段存放微信特有信息（群名等），KnowWind 不感知，原样保存。

---

## 后台服务接口

服务监听 `http://localhost:8001`，完整接口列表：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查，KnowWind 用来确认插件在线 |
| GET | `/info` | 插件信息（名称、版本、UI 入口路径） |
| GET | `/strategy-templates` | 返回所有策略模板 |
| GET | `/groups` | 返回所有群列表（含策略配置） |
| POST | `/groups/sync` | 从 wechat-decrypt 同步群列表 |
| POST | `/groups/{id}/strategy` | 更新某个群的策略（label / extra / enabled） |
| POST | `/collect` | 触发采集 |
| GET | `/collect/status` | 查询当前采集进度 |
| POST | `/feedback` | 接收 KnowWind 用户反馈，自动更新策略 |

---

## 脚本职责

| 脚本 | 职责 |
|------|------|
| `.env` | 用户配置 |
| `server/main.py` | 后台服务入口（FastAPI，监听 localhost:8001） |
| `server/insights.py` | 核心业务：规则过滤 + LLM 精提取 + 推送 |
| `server/db.py` | SQLite 操作（群表、日志表） |
| `ui/index.html` | 配置界面（Vue 3 CDN，注册进 KnowWind 导航） |
| `scripts/extract-insights.py` | 独立 CLI 工具：stdin 消息 → stdout insights |
| `scripts/push-insights.py` | 独立 CLI 工具：stdin insights → 推送 KnowWind |

---

## 安全要求

`all_keys.json`（wechat-decrypt 生成的本机微信数据库密钥）严禁：
- 打印到终端
- 上传到任何服务
- 提交到 Git
- 写进日志

`.env` 包含个人配置，已加入 `.gitignore`，不会被提交。

---

## 常见问题排查

### wechat-decrypt 连不上

```bash
# macOS
sudo ./find_all_keys_macos
curl -s http://localhost:5678/ | head -c 200

# 重新启动服务
cd /path/to/wechat-decrypt
sudo ./find_all_keys_macos
python3 main.py
```

### 群同步后无群

```bash
# 确认 wechat-decrypt 有消息
curl -s 'http://localhost:5678/api/history?limit=10'

# 确认 GROUP_KEYWORDS 能匹配到群名（空值=采集全部）
grep GROUP_KEYWORDS .env
```

### 提取出的 insights 数量为 0

- 确认目标群最近有消息（`since` 时间戳是否正确）
- 检查候选消息数量（`/logs` 接口的 `candidate_count` 字段）
- 确认 LLM 可用：`claude --version` 或 `echo $ANTHROPIC_API_KEY`

### LLM 调用失败

```bash
# 检查 claude CLI 是否可用
claude --version

# 检查 Anthropic SDK 是否配置
echo $ANTHROPIC_API_KEY
```

两者都没有时，自动退化为纯规则提取（score=50）。

### KnowWind 推送失败

```bash
# 检查 KnowWind 服务是否在运行
curl -s http://localhost:8000/health

# 查看最近采集日志
curl http://localhost:8001/logs?limit=5
```

