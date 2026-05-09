# FastAPI 后台服务与 LLM 提取流水线 需求文档

**创建日期：** 2026-05-09
**项目：** wx-still
**功能模块：** FastAPI 后台服务 + SQLite 数据库 + Vue 管理界面 + LLM 提取流水线

## 一、需求概述

将 wx-still 从纯 bash 脚本工作流改造为可被 KnowWind 管理的后台插件服务。提供 HTTP API 供 KnowWind 触发采集、管理群配置、接收点评反馈。消息来源从旧的 wx-cli 切换为 wechat-decrypt HTTP API。

## 二、功能结构

### 后台服务（server/）
- FastAPI 应用，监听 localhost:8001
- 插件注册：启动时向 KnowWind `POST /api/plugins/register`
- 配置加载：从 config.sh 解析 env 变量（Python 正则，无需 bash source）

### API 路由
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /info | 插件信息 |
| GET | /groups | 群列表（含策略配置） |
| POST | /groups/{id}/strategy | 更新群策略（label/extra/enabled） |
| POST | /groups/sync | 从 wechat-decrypt 同步群列表 |
| POST | /collect | 触发采集（后台线程） |
| GET | /collect/status | 采集进度查询 |
| POST | /feedback | 接收 KnowWind 点评 |
| GET | /logs | 采集日志 |

### 数据库（SQLite）
- `groups` 表：群配置（id, name, enabled, strategy_label, strategy_extra, strategy_feedback, last_fetched_at）
- `fetch_logs` 表：采集记录（message_count, candidate_count, insight_count, pushed_count, status, error）

### 配置界面（Vue 3 CDN）
- 群列表：toggle 启用/停用，策略配置面板
- 采集触发：状态 pill 实时展示，3 秒轮询

### LLM 提取流水线（server/insights.py）
- 规则粗过滤（系统消息、表情、短文本、过滤词）
- LLM 精提取（claude CLI → Anthropic SDK → 规则降级）
- 敏感话题过滤（翻墙/VPN 等）
- 推送 KnowWind REST API

## 三、数据来源

- **消息来源**：wechat-decrypt HTTP API（localhost:5678）
  - `GET /api/history?since={ts}&chat={name}&limit=2000`
  - 按 `is_group` 字段过滤群消息
  - 按 `GROUP_KEYWORDS` 过滤目标群
- **群发现**：从历史消息中提取 `is_group=true` 的 chat/username 对

## 四、技术要求

- Python 3.10+，FastAPI + uvicorn + httpx
- SQLite（stdlib），无 ORM
- Vue 3 CDN，无构建步骤
- LLM：优先 claude CLI，备选 Anthropic SDK，降级纯规则
- 安装：uv venv + uv pip install（macOS PEP 668 限制）

## 五、安全要求

- 发言人（sender 字段）采集后立即丢弃，不写入任何文件或日志
- 推送给 KnowWind 的数据不含微信 ID 或群成员昵称
- config.sh 不提交 Git

## 六、验证标准

- `curl localhost:8001/health` → `{"status":"ok"}`
- `POST /groups/sync` 从 wechat-decrypt 同步群，数量正确
- `POST /collect` 触发，状态从 running → success/failed
- `extract-insights.py` 独立运行：1 条候选 → 1 条 LLM insight
- 日志记录 candidate_count、insight_count、pushed_count

## 七、参考资料

- wechat-decrypt API：`GET /api/history` 返回字段见 TECH.md
- KnowWind 插件接口规范：TECH.md §推送规范
- AGENTS.md：操作规则、提取规则、策略说明
