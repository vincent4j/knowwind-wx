# wx-still 操作规则手册

> 本文件是微信插件的完整规则手册。AI 每次操作前必须读这份文件。

---

## 项目定位

`wx-still` 是 KnowWind 决策平台的微信数据源插件。

职责：从本机微信群采集消息 → 规则粗过滤 → LLM 精提取 → 推送给 KnowWind。

完整架构见 `knowwind/docs/DESIGN.md`。

---

## 配置文件

所有用户相关配置集中在项目根目录的 `config.sh`。脚本启动时自动 `source` 它。

```bash
cp config.example.sh config.sh
# 编辑 config.sh，至少改以下三项：
#   FEISHU_DOC_URL        飞书文档完整 URL（将来版本用，当前可留空）
#   WECHAT_DECRYPT_URL    wechat-decrypt 服务地址（默认 http://localhost:5678）
#   GROUP_KEYWORDS        目标微信群名称关键词（逗号分隔）
```

可选配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TMP_DIR` | `/private/tmp` | 临时文件目录 |
| `SESSION_WINDOW` | `900`（15 分钟） | 同一问题的消息合并时间窗口（秒） |
| `ANSWER_WINDOW` | `900`（15 分钟） | 答案关联到问题的时间窗口（秒） |
| `MIN_QUESTION_LENGTH` | `8` | 有效问题的最短字符数 |
| `ANTHROPIC_MODEL` | `claude-opus-4-5` | LLM 精提取使用的模型 |
| `KNOWWIND_URL` | `http://localhost:8000` | KnowWind 核心平台地址（推送目标） |

---

## 环境依赖

### wechat-decrypt

- GitHub：https://github.com/ylytdeng/wechat-decrypt
- 服务地址由 `config.sh` 中的 `WECHAT_DECRYPT_URL` 指定（默认 `http://localhost:5678`）
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

- Python 3.10+，无需额外依赖

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
- 临时文件只放在 `TMP_DIR`（默认 `/private/tmp`）
- 输出 insights 时，不保留发言人、微信 ID、群成员昵称

---

## 数据流

```
wechat-decrypt HTTP API
        ↓
export-wechat-groups.sh
（拉取当天增量消息，写入 wx_messages_DATE.json）
        ↓
extract-insights.py 第一步：规则粗过滤
（过滤系统消息、表情、短句，命中关键词进候选池）
        ↓
extract-insights.py 第二步：LLM 精提取
（候选消息批量送 LLM，输出结构化 insights + 评分）
        ↓
push-insights.py
（推送给 KnowWind REST API）
```

---

## 采集机制

- **增量采集**：记录上次采集时刻（`last_fetched_at`），每次只拉取之后的新消息
- **触发方式**：人工触发（界面按钮或对话输入），不自动定时
- **群过滤**：从 wechat-decrypt 拉取全量消息后，按 `GROUP_KEYWORDS` 过滤目标群

wechat-decrypt API 调用方式：
```
GET {WECHAT_DECRYPT_URL}/api/history?since={last_fetched_at}&limit=2000
```

---

## 提取规则

### 第一步：规则粗过滤

以下消息直接丢弃：
- 消息类型为 `system`（系统消息）
- 消息类型为 `emoji`（纯表情）
- 文本长度 < `MIN_QUESTION_LENGTH`（默认 8 字）
- 内容命中过滤关键词：`拍了拍`、`撤回了`、`加入了群聊`、`邀请`、`修改群名`

命中以下任意关键词，进入候选池：
```
请问 问下 问一下 想问 怎么 如何 为什么 为啥
能不能 有没有 可以吗 报错 安装 登录 提交
无法 不显示 不能 失败 错误 问题 #举手 ？ ?
```

### 第二步：LLM 精提取

输入：候选消息批量 + 策略提示词（标签模板 + 用户补充 + 历史反馈）

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

问题标题命中以下关键词，整条丢弃（不推送给 KnowWind）：
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

策略存储在本地数据库（SQLite），每个群独立配置。

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

## 脚本职责

| 脚本 | 职责 |
|------|------|
| `config.sh` | 用户配置 |
| `scripts/export-wechat-groups.sh` | 调用 wechat-decrypt API，增量拉取目标群消息 |
| `scripts/extract-insights.py` | 规则粗过滤 + LLM 精提取，输出结构化 insights |
| `scripts/push-insights.py` | 推送 insights 给 KnowWind REST API |
| `scripts/run-daily.sh` | 总入口，串联以上步骤 |

---

## 临时文件命名规范

所有临时文件放在 `TMP_DIR`（默认 `/private/tmp`）：

| 文件 | 说明 |
|------|------|
| `wx_messages_YYYY-MM-DD.json` | wechat-decrypt 导出的原始消息 |
| `wx_insights_YYYY-MM-DD.json` | 提取后的结构化 insights（供核查） |

脚本运行完成后，`.json` 临时文件自动删除；如需保留供核查，使用 `--keep-tmp` 参数。

---

## 安全要求

`all_keys.json`（wechat-decrypt 生成的本机微信数据库密钥）严禁：
- 打印到终端
- 上传到任何服务
- 提交到 Git
- 写进日志

`config.sh` 包含个人配置，已加入 `.gitignore`，不会被提交。

---

## 常见问题排查

### wechat-decrypt 连不上

```bash
# macOS
sudo ./find_all_keys_macos
# Windows / Linux：直接跳过此步
curl -s http://localhost:5678/api/history | head -c 200

# 重新启动服务
cd /path/to/wechat-decrypt
sudo ./find_all_keys_macos
python3 main.py
```

### 提取出的 insights 数量为 0

- 检查 `wx_messages_DATE.json` 是否有内容
- 检查目标群关键词是否匹配（`config.sh` 中的 `GROUP_KEYWORDS`）
- 检查日期是否正确

### LLM 调用失败

```bash
# 检查 claude CLI 是否可用
claude --version

# 检查 Anthropic SDK 是否配置
echo $ANTHROPIC_API_KEY
```

两者都没有时，自动退化为纯规则提取。

### KnowWind 推送失败

```bash
# 检查 KnowWind 服务是否在运行
curl -s http://localhost:8000/health
```
