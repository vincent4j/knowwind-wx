# 微信群 QA 整理工作规则

> 本文件是项目的完整规则手册。AI 每次操作前必须读这份文件。

---

## 目标

使用本机 `wx-cli` 读取微信群消息，整理「超级 AI 大航海」相关微信群里的问题，每天写入指定飞书文档。

目标不是自动回复，也不是实时监听，而是定期整理微信群中的高价值问题。

---

## 配置文件

所有用户相关配置集中在项目根目录的 `config.sh`。脚本启动时自动 `source` 它，无需手动设置环境变量。

```bash
cp config.example.sh config.sh
# 编辑 config.sh，至少改以下三项：
#   FEISHU_DOC_URL   飞书文档完整 URL
#   WX_CLI_PATH      wx-cli 可执行文件路径
#   GROUP_KEYWORDS   目标微信群名称关键词（逗号分隔）
```

可选配置项（有默认值，一般不需要改）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TMP_DIR` | `/private/tmp` | 临时文件目录 |
| `SESSION_WINDOW` | `900`（15 分钟） | 同一问题的消息合并时间窗口（秒） |
| `ANSWER_WINDOW` | `900`（15 分钟） | 答案关联到问题的时间窗口（秒） |
| `MIN_QUESTION_LENGTH` | `8` | 有效问题的最短字符数 |
| `ANTHROPIC_MODEL` | `claude-opus-4-5` | 跨天去重使用的 LLM 模型 |

---

## 环境依赖

### wx-cli

- 路径由 `config.sh` 中的 `WX_CLI_PATH` 指定
- 只能在本机 macOS 用户环境运行，不上服务器，不进 Docker
- `wx init` 需已完成，`~/.wx-cli/all_keys.json` 需已生成
- 如路径失效，重新安装但不要改微信数据库

### lark-cli

- 路径由脚本自动探测：优先 `PATH`，其次 `~/.nvm/versions/node/*/bin/lark-cli`（取最新版本）
- 需已登录飞书账号（`lark-cli auth status` 验证）
- `--markdown @filename` 必须用相对路径，需先 `cd` 到文件所在目录

### Python

- Python 3.10+，无需额外依赖

---

## 工具边界

- 不修改 wx-cli 源码
- 不重新实现微信数据库读取逻辑
- 不采集无关微信群
- 不做自动回复
- 不保存完整聊天原文到项目目录
- 临时文件只放在 `TMP_DIR`（默认 `/private/tmp`）
- 输出到飞书时，不保留发言人、微信 ID、群成员昵称

---

## 目标群范围

目标群关键词在 `config.sh` 的 `GROUP_KEYWORDS` 中配置，群名包含任意一个关键词即纳入。

脚本运行时会自动从 `wx sessions` 中过滤出目标群，无需手动维护群 ID 列表。

---

## QA 提取规则

### 问题识别关键词

命中以下任意关键词的文本消息，视为问题候选：

```
请问 问下 问一下 想问 怎么 如何 为什么 为啥
能不能 有没有 可以吗 报错 安装 登录 提交
无法 不显示 不能 失败 错误 问题 #举手 ？ ?
```

### 过滤规则

以下消息直接丢弃：

- 系统消息（拍一拍、加入群聊、撤回、修改群名等）
- 纯表情消息
- 长度 < 8 字的短句
- 自我介绍、纯感谢、闲聊

### 敏感话题过滤

问题标题命中以下关键词，整条丢弃（不写入飞书）：

```
科学上网 梯子 翻墙 VPN vpn 代理 上科技
机场 节点 clash Clash shadowsocks v2ray trojan
```

注意：过滤只作用于问题标题，不影响答案内容。

### 无答案过滤

问题后 15 分钟内，没有任何 ≥ 10 字的文本回复，整条丢弃。

---

## 频次与对话数统计口径

| 指标 | 定义 |
|---|---|
| 出现次数 | 同一问题被问了几次。15 分钟内的重复提问算 1 次；超过 15 分钟后再次出现算新的 1 次 |
| 对话次数 | 该问题引发的消息总条数（含提问和回复）。文本、图片、文件、链接各算 1 条；系统消息、拍一拍、纯表情不计入 |

展示格式：

```
频次：出现 N 次，累计 M 条对话
```

---

## 排序规则

### 每日块内问题排序

1. 出现次数从高到低
2. 出现次数相同，按最早出现时间升序

### 总目录排序

1. 出现次数从高到低
2. 出现次数相同，按对话次数从高到低

---

## 飞书文档格式规范

### 文档地址

由 `config.sh` 中的 `FEISHU_DOC_URL` 指定。

### 文档结构

```
[顶部说明段落]            ← 怎么用 + 数据口径 + 数据来源（固定，不随每日更新）
## 📚 总目录              ← 所有问题列表（含锚点链接）
## 2026-05-09：N 个问题
  ### Q1：问题标题
  ### Q2：问题标题
  ...
---
## 2026-05-08：N 个问题
  ...
```

### 顶部说明（固定内容，不随每日更新变动）

```
📖 怎么用：按 Ctrl+F（Mac 用 Cmd+F）全局搜索关键词，快速定位你想找的问题。

📊 数据口径：出现次数 = 同一个问题在群里被问了几次（15 分钟内的重复提问算 1 次）；
对话次数 = 该问题引发的消息总条数（含提问和回复）。

📌 数据来源：（由维护者填写）
```

### 总目录

- 列出**所有**问题，不限于高频（包括只出现 1 次的）
- 每条带锚点链接，点击直接跳转到对应问题块
- 排序：出现次数降序；同频按对话次数降序
- 不显示 Q 编号前缀
- 条目格式：`- [问题标题（出现 N 次，N 条对话）](锚点链接)`

### 每日块标题格式

```markdown
## 2026-05-09：10 个问题
```

不加「N 群汇总」等后缀。

### 每个问题格式

```markdown
### Q1：问题标题

频次：出现 N 次，累计 M 条对话

群里的回答：这里是群里的原始回复内容，不做 AI 总结。

资料：
- 资源名称：https://example.com
```

格式要求：

- `频次：` 和 `群里的回答：` 均为纯文字，不加 `**` 加粗
- 答案内容不含内联链接，所有链接统一放到 `资料：` 区块
- 没有链接的问题不显示 `资料：` 区块
- 没有文字回复的问题**不写入飞书**
- 不写发言人、微信 ID、群成员昵称

---

## 跨天重复问题处理

同一个问题昨天出现过、今天又有人问，处理流程：

1. 脚本自动调用 LLM 判断今天的问题与历史问题是否语义相同
2. 展示疑似重复对，由用户逐一确认（`y` = 是同一个 / `n` = 不同问题 / `s` = 跳过）
3. 确认为同一个：更新历史块的频次和对话数，今天不重复写这条
4. 确认为不同：今天正常追加

---

## 增量拉取新消息

当天已经运行过一次后，如需拉取指定时间点之后的新消息：

1. **确认数据截止时间**：查看 `wx_qa_export_DATE.json` 中最新一条消息的 `timestamp`
2. **拉取当天全量**：`wx export GROUP --since DATE --until DATE --format json --limit 2000`（`--since/--until` 只支持到日期，不支持到秒）
3. **Python 过滤**：只保留 `timestamp > 截止时间` 的消息
4. **合并**：将新消息追加到 `wx_qa_export_DATE.json`，按 timestamp 去重并排序
5. **重跑提取**：重新运行 `extract-qa.py --date DATE`，它会处理合并后的全量数据

注意：`wx_qa_export_DATE.json` 如果不存在（被清理过），需先从 `wx_super_ai_histories.jsonl`（如果存在）重建，再合并新消息。

---

## 追加模式（保护手动修改）

每次运行默认为**追加模式**，不覆盖已有内容：

- 脚本先拉取飞书文档，对比今天已有的问题标题
- 只追加文档中不存在的新问题
- 已有问题（包括你手动修改过的答案）**不会被覆盖**
- 当天可多次运行，每次只追加增量

如需全量重写当天块（会覆盖手动修改），使用 `--force`：

```bash
./scripts/write-feishu-doc.sh --date 2026-05-09 --force
```

---

## 脚本职责

| 脚本 | 职责 |
|---|---|
| `config.sh` | 用户配置（飞书文档、wx-cli 路径、群关键词等） |
| `scripts/export-wechat-groups.sh` | 调用 wx-cli，导出目标群消息到 `TMP_DIR` |
| `scripts/extract-qa.py` | 提取问题、合并、计算频次和对话条数，输出 `.md` 和 `.json` |
| `scripts/merge-qa.py` | 拉取飞书历史问题，LLM 判断跨天重复，输出追加/更新计划 |
| `scripts/write-feishu-doc.sh` | 调用 lark-cli，追加新问题、更新历史频次、更新总目录 |
| `scripts/run-daily-qa.sh` | 总入口，串联以上步骤，写入前等待用户确认 |

---

## 临时文件命名规范

所有临时文件放在 `TMP_DIR`（默认 `/private/tmp`），命名格式：

| 文件 | 说明 |
|---|---|
| `wx_qa_export_YYYY-MM-DD.json` | wx-cli 导出的原始消息 |
| `wx_qa_groups_YYYY-MM-DD.json` | 本次处理的群列表 |
| `wx_qa_YYYY-MM-DD.md` | 提取后的 QA Markdown（保留供人工核查） |
| `wx_qa_YYYY-MM-DD.json` | 提取后的 QA 结构化数据（供 merge-qa.py 使用） |
| `wx_qa_append_plan_YYYY-MM-DD.json` | 本次需追加的新问题列表 |
| `wx_qa_update_plan_YYYY-MM-DD.json` | 本次需更新频次的历史问题列表 |

脚本运行完成后，`.json` 临时文件自动删除；`.md` 文件保留供人工核查。

---

## lark-cli 操作规范

### 写入策略

| 操作 | 使用方式 |
|---|---|
| 追加新问题到当天块末尾 | `--selection-by-title "## 标题" --mode insert_after` |
| 新建当天块（首次） | `--selection-by-title "## 上一天标题" --mode insert_before` |
| 更新某个 Q 块的频次行 | `--selection-with-ellipsis "### Q1：标题...### Q2：下一个标题" --mode replace_range`（精确选中范围） |
| 更新总目录 | `--selection-with-ellipsis "## 总目录标题...## 第一个日期块标题" --mode replace_range`，新内容包含完整 TOC（标题 + 所有列表项）；这是替换整个 TOC 区块（含列表项）的唯一安全方式 |
| 更新日期块标题（问题数量） | 只对 h2 标题行单独做 `replace_range`，**不能**对整个 h2 块操作（会清空块内所有内容） |

### 注意事项

- `--markdown @filename` 必须用相对路径，先 `cd` 到文件所在目录再执行
- **h3 块操作高危**：`delete_range` 和 `replace_range` 作用于 h3 块时，会连同块内所有内容一起删除，不只是标题行。重命名 h3 标题的唯一安全方式：用 `--selection-with-ellipsis "### 旧标题...下一个标题"` 精确选中范围做 `replace_range`，新内容包含新标题行和原有内容
- 总目录的锚点链接（`#BLOCK_ID`）在每次 `replace_range` 后会失效，需重新拉取 outline 获取新 block ID
- 总目录标题带 Feishu 格式标记（如 `<text bgcolor="light-yellow">`）时，`selection-with-ellipsis` 的起始部分需包含完整标记字符串

---

## 安全要求

`~/.wx-cli/all_keys.json` 是本机微信数据库密钥，严禁：

- 打印到终端
- 上传到任何服务
- 提交到 Git
- 写进日志
- 发给任何外部服务

`config.sh` 包含飞书文档地址等个人配置，已加入 `.gitignore`，不会被提交。

---

## 完整执行流程

```
run-daily-qa.sh
│
├─ 1. export-wechat-groups.sh
│     └─ wx sessions → 过滤目标群 → wx history 逐群导出
│        → wx_qa_export_DATE.json（所有群消息合并）
│
├─ 2. extract-qa.py
│     └─ 过滤系统消息/表情 → 识别问题候选 → 过滤敏感/无答案
│        → 合并相似问题 → 计算频次和对话数 → 排序
│        → wx_qa_DATE.md + wx_qa_DATE.json
│
├─ 3. 预览（问题数、群数、前 3 条样例）→ 等待用户输入 y 确认
│
└─ 4. write-feishu-doc.sh
      ├─ 步骤 1：merge-qa.py 跨天去重
      │          └─ 拉取飞书历史 → LLM 判断重复 → 用户逐一确认
      │             → append_plan.json + update_plan.json
      ├─ 步骤 2：更新历史问题频次（仅改频次行，不动其他内容）
      ├─ 步骤 3：追加今天新问题（跳过已存在的）+ 更新日期块标题
      └─ 步骤 4：重建总目录（含新锚点链接）
```

---

## 常见问题排查

### wx-cli 连不上 / `wx sessions` 报错

```bash
# 检查 daemon 是否在运行
cat ~/.wx-cli/daemon.log

# 重启 daemon
/path/to/wx daemon restart

# 确认微信桌面版已登录且在前台运行
```

### lark-cli 写入失败（`"ok": false`）

```bash
# 检查登录状态
lark-cli auth status

# 重新登录
lark-cli auth login

# 确认文档 URL 正确（config.sh 中的 FEISHU_DOC_URL）
```

### 提取出的问题数量为 0

- 检查 `wx_qa_export_DATE.json` 是否有内容（`wc -l /private/tmp/wx_qa_export_DATE.json`）
- 检查目标群关键词是否匹配（`config.sh` 中的 `GROUP_KEYWORDS`）
- 检查日期是否正确（群里当天是否有消息）

### 跨天去重 LLM 调用失败

```bash
# 检查 claude CLI 是否可用
claude --version

# 检查 anthropic SDK 是否配置
echo $ANTHROPIC_API_KEY

# 如果两者都没有，去重步骤会自动跳过，今天所有问题直接追加
```

### 飞书文档内容被意外清空

原因：对 h2 或 h3 块使用了 `replace_range`，导致块内所有内容被清除。

恢复方式：
1. 从 `wx_qa_DATE.md`（保留在 `/private/tmp`）找到原始内容
2. 用 `insert_after` 逐条重新写入（不要用 `replace_range`）
3. 更新总目录锚点链接（需重新拉取 outline 获取新 block ID）
