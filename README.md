# 微信群 QA 整理工具

从指定微信群中提取高价值问答，每天汇总写入飞书文档。

---

## 文件结构

```
weixin-agent/
├── config.example.sh          # 配置模板（提交到 Git）
├── config.sh                  # 你的个人配置（不提交，需自行创建）
├── AGENTS.md                  # 完整规则手册（AI 操作前必读）
├── README.md                  # 本文件
└── scripts/
    ├── run-daily-qa.sh        # 每日入口，串联所有步骤
    ├── export-wechat-groups.sh # 从微信导出目标群消息
    ├── extract-qa.py          # 提取、过滤、合并问题
    ├── merge-qa.py            # 跨天去重（LLM 判断 + 用户确认）
    └── write-feishu-doc.sh    # 写入飞书文档
```

---

## 前提条件

**运行本工具必须先安装以下两个工具，缺一不可。**

### wx-cli（读取微信消息）

GitHub：https://github.com/jackwener/wx-cli  
要求：macOS + 微信桌面版已登录

```bash
mkdir -p /private/tmp/wx-cli-check
cd /private/tmp/wx-cli-check
npm install @jackwener/wx-cli

# 初始化（读取本机微信数据库密钥，只需做一次）
./node_modules/.bin/wx init

# 验证安装成功（应列出你的微信会话）
./node_modules/.bin/wx sessions
```

> `wx init` 会在 `~/.wx-cli/all_keys.json` 生成密钥文件，**不要分享、不要提交 Git**。

### lark-cli（写入飞书文档）

GitHub：https://github.com/larksuite/cli  
npm：https://www.npmjs.com/package/@larksuite/cli

```bash
npm install -g @larksuite/cli

# 登录飞书账号
lark-cli auth login

# 验证登录成功
lark-cli auth status
```

### 其他要求

| 工具 | 要求 |
|---|---|
| macOS | 必须在本机运行，不支持服务器/Docker |
| 微信桌面版 | 需已登录 |
| Python 3.10+ | 系统内置，无需额外安装 |
| Node.js | 安装 lark-cli 需要 |

---

## 初始配置

克隆项目后，只需改一个文件：

```bash
cp config.example.sh config.sh
```

然后编辑 `config.sh`，必改以下三项：

| 配置项 | 说明 | 示例 |
|---|---|---|
| `FEISHU_DOC_URL` | 目标飞书文档的完整 URL | `https://xxx.feishu.cn/docx/ABC123` |
| `WX_CLI_PATH` | wx-cli 可执行文件的绝对路径 | `/private/tmp/wx-cli-check/node_modules/.bin/wx` |
| `GROUP_KEYWORDS` | 目标微信群名称关键词，逗号分隔，群名包含任意一个即纳入 | `AI大航海,5月航海` |

其他配置项有默认值，一般不需要改。`config.sh` 已加入 `.gitignore`，不会被提交。

---

## LLM 配置（跨天去重用）

跨天去重需要调用 LLM 判断今天的问题是否与历史问题语义相同。按以下任一方式配置：

**方式 A：使用 claude CLI（推荐，免费额度更高）**

```bash
npm install -g @anthropic-ai/claude-code
claude  # 首次运行会引导登录
```

**方式 B：使用 Anthropic Python SDK**

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

> 如果两种方式都没有配置，跨天去重步骤会自动跳过，今天所有问题直接追加。

---

## 每日使用

```bash
# 整理今天的 QA 并写入飞书（标准用法）
./scripts/run-daily-qa.sh

# 整理指定日期
./scripts/run-daily-qa.sh --date 2026-05-09

# 只预览，不写入飞书
./scripts/run-daily-qa.sh --dry-run

# 跳过导出步骤（复用已有的导出文件，适合重跑）
./scripts/run-daily-qa.sh --skip-export
```

运行过程中会：
1. 自动导出目标群当天消息
2. 提取、合并、过滤问题
3. 调用 LLM 检查是否与历史问题重复（需逐一确认）
4. 预览本次写入内容，等待你输入 `y` 确认
5. 追加新问题到飞书文档（不覆盖你已手动修改的内容）

---

## 怎么给 AI 发指令

以下是常用的指令模式，直接复制发给 AI 即可。

**拉取当天增量（最常用）**
```
拉取今天最新消息，看有没有新问题
```
AI 会自动查当前数据截止时间，拉增量，过滤噪音，预览后写入飞书。

**处理指定日期**
```
整理 2026-05-10 的问题，写入飞书
```

**手动追加一条问题**
```
在飞书 05-09 区块追加一个问题：[问题标题] / 答案：[答案内容]
```

**修改某条问题的数据**
```
把 05-09 Q1 的对话次数改成 24
```

**重建总目录**
```
重新生成总目录，按规则排序
```

---

## 注意事项

- **手动修改保护**：脚本默认只追加新问题，不覆盖已有内容。可以放心在飞书文档里修改答案。
- **当天多次运行**：安全，每次只追加增量。
- **强制全量重写**：`./scripts/write-feishu-doc.sh --date 2026-05-09 --force`（会覆盖手动修改，慎用）
- **临时文件**：所有中间文件在 `TMP_DIR`（默认 `/private/tmp`），脚本运行完自动清理 JSON，`.md` 文件保留供核查。

---

## 详细规则

见 [AGENTS.md](./AGENTS.md)，包含：完整提取规则、频次口径、飞书文档格式规范、lark-cli 操作规范、常见问题排查等。
