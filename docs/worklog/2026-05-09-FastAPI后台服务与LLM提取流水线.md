# 工作日志 - 2026-05-09

## 项目：wx-still - FastAPI 后台服务与 LLM 提取流水线

## 一、任务概述

将 wx-still 从纯 bash 脚本工作流（export → extract → merge → write-feishu）改造为可被 KnowWind 管理的 HTTP 插件服务。核心目标：持久化群配置、HTTP 触发采集、LLM 提取 insights、推送 KnowWind。

## 二、完成的工作

**新增文件：**
- `requirements.txt` — fastapi, uvicorn, httpx
- `server/__init__.py` — Python 包标记
- `server/db.py` — SQLite CRUD（groups + fetch_logs 表）
- `server/main.py` — FastAPI 应用，9 个路由，config.sh 解析，KnowWind 注册
- `server/insights.py` — 规则过滤 + LLM 提取（claude CLI/SDK/降级）+ 推送逻辑
- `ui/index.html` — Vue 3 CDN 管理界面（群列表、策略配置、采集触发、日志）
- `scripts/extract-insights.py` — 独立命令行包装（stdin/stdout）
- `scripts/push-insights.py` — 独立命令行包装

**删除文件：**
- `scripts/export-wechat-groups.sh` — 依赖 wx-cli（用户不使用）
- `scripts/run-daily-qa.sh` — 依赖 wx-cli 的总入口脚本

**重要决策：**
- 群列表同步：无 /sessions 端点，从 `/api/history?limit=2000` 消息中提取 `is_group=true` 的群
- LLM 调用：优先 claude CLI（`-p` 参数），备选 Anthropic SDK，降级纯规则
- config.sh 解析：Python 正则（无 bash source），env 变量优先

## 三、遇到的问题和解决方案

**问题 1：用户不使用 wx-cli**
- 初始方案调用了 wx-cli（`$WX sessions --json`），用户明确指出不用 wx-cli，要求删除所有相关代码
- 解决：深入阅读 wechat-decrypt 源码（GitHub），发现只有 `/api/history` 端点，无群列表端点；改为从消息历史提取群

**问题 2：macOS PEP 668 系统 Python 禁止 pip**
- `pip install` 报 externally-managed-environment 错误
- 解决：改用 `uv venv .venv && uv pip install`

**问题 3：端口 8001 被占**
- 前一次测试的 uvicorn 进程残留
- 解决：`pkill -f "uvicorn server.main"` 清理，重启

**问题 4：`python` 命令不存在**
- macOS 默认只有 `python3`
- 解决：全程使用 `.venv/bin/python` 或 `.venv/bin/uvicorn`

## 四、本次对话复盘

### 4.1 问题识别

核心错误出在对数据源的假设上：初始实现假设 wechat-decrypt 有群列表接口，且用户在使用 wx-cli，两个假设都错了。

### 4.2 根因分析

没有在编码前验证 wechat-decrypt 的实际 API 端点。看了 README 但没看 `main.py` 源码，导致设计了不存在的接口调用。

### 4.3 解决过程

用户指出 wx-cli 问题后，通过 `agent-reach` 技能直接拉取 wechat-decrypt 源码（`monitor_web.py`），确认只有 4 个真实端点，然后重新设计群发现逻辑。

### 4.4 经验教训

1. **集成第三方服务前，先验证其实际 API**：不要凭 README 设计，要看源码或实际测试
2. **用户说"你好好看 readme"时，是在提示需要读更深层的文档**：需要主动获取源码而非只看高层描述
3. **架构变更要明确问用户**：从 wx-cli 改到 wechat-decrypt 是破坏性变更，应先确认再实施

### 4.5 预防措施

对于每个外部 HTTP 服务，编码前先运行 `curl -s {URL}/` 或读源码，确认实际可用端点列表。

## 五、创建/修改的文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `requirements.txt` | 新增 | fastapi, uvicorn, httpx |
| `server/__init__.py` | 新增 | 空文件 |
| `server/db.py` | 新增 | SQLite CRUD |
| `server/main.py` | 新增 | FastAPI 主服务 |
| `server/insights.py` | 新增 | LLM 提取 + 推送逻辑 |
| `ui/index.html` | 新增 | Vue 3 CDN 管理界面 |
| `scripts/extract-insights.py` | 新增 | 独立提取脚本 |
| `scripts/push-insights.py` | 新增 | 独立推送脚本 |
| `scripts/export-wechat-groups.sh` | 删除 | wx-cli 依赖 |
| `scripts/run-daily-qa.sh` | 删除 | wx-cli 依赖 |

## 六、技术栈/技术决策

- **FastAPI** over Flask：更好的类型支持、自动 OpenAPI 文档
- **SQLite + stdlib**：无需 ORM，schema 简单稳定
- **Vue 3 CDN**：无构建步骤，与 FastAPI StaticFiles 集成简单
- **uv** 替代 pip：macOS PEP 668 约束下唯一可靠方案
- **claude CLI 优先**：复用已有登录账号，无需额外 API key

## 七、下一步工作

1. `/feedback` 路由：加 LLM 转换（原话 → 策略规则一句话）
2. 删除旧脚本：`scripts/extract-qa.py`、`scripts/merge-qa.py`、`scripts/write-feishu-doc.sh`
3. 补全 `config.example.sh`：加 `KNOWWIND_URL` 和 `KNOWWIND_TOKEN`
4. 真实数据联调：wechat-decrypt 在线时测试完整流程

## 八、备注

- 服务启动：`.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8001`
- 旧脚本 `extract-qa.py`/`merge-qa.py` 暂未删除，可在下次对话清理

---

## 快速摘要（用于下次对话）

**完成：** 从零搭建 wx-still FastAPI 后台服务，含 SQLite 群配置、Vue 管理 UI、LLM 提取流水线（claude CLI → SDK → 规则降级）、推送 KnowWind

**问题：** 初始误用 wx-cli + 假设了不存在的群列表端点 → 读 wechat-decrypt 源码后，改为从 `/api/history` 消息中提取 is_group 群

**经验：** 集成第三方 HTTP 服务前先验证实际端点（读源码/curl 测试），不要只看 README；外部服务架构假设错误代价高

**下一步：** /feedback 加 LLM 策略转换；删旧脚本（extract-qa.py 等）；补全 config.example.sh；wechat-decrypt 在线时联调真实数据

**文件：** server/main.py, server/db.py, server/insights.py, ui/index.html, scripts/extract-insights.py, scripts/push-insights.py（删：export-wechat-groups.sh, run-daily-qa.sh）
