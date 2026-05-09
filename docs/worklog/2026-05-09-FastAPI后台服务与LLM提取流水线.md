# 工作日志 - 2026-05-09

## 项目：wx-still - FastAPI 后台服务与 LLM 提取流水线

## 一、任务概述

继续上次工作：完成配置迁移、删旧脚本、feedback 策略转换，并进行真实数据联调，打通完整采集链路。

## 二、完成的工作

1. **配置迁移**：`config.sh` → `python-dotenv`，删除 `config.example.sh`，新增 `.env.example`
2. **删旧脚本**：删除 `scripts/extract-qa.py`、`merge-qa.py`、`write-feishu-doc.sh`
3. **feedback 策略转换**：`insights.py` 新增 `derive_strategy_from_feedback()`，`/feedback` 端点调用 LLM 分析反馈并自动更新策略
4. **消息类型 bug 修复**：`_is_candidate` 只接受英文 `"text"`，但 wechat-decrypt 返回中文类型名（`"文本"`、`"链接/文件"`）→ 修复为支持中英文类型
5. **真实数据联调**：完整跑通 wechat-decrypt → 消息拉取 → 规则过滤 → LLM 提取 → 写 log 全链路

## 三、遇到的问题和解决方案

### 问题 1：消息类型不匹配导致 candidate_count 始终为 0

**现象**：collect 跑完，message_count 有值，但 candidate_count 和 insight_count 都是 0。

**根因**：`_is_candidate` 里 `msg_type != "text"` 用的是英文，而 wechat-decrypt 实际返回 `"文本"` 和 `"链接/文件"`（中文）。

**解决**：定义 `_TEXT_TYPES = {"text", "文本", "链接/文件"}`，改为 `msg_type not in _TEXT_TYPES`。

### 问题 2：collect 跑完但 log 没有新记录（误判）

**现象**：`/logs` API 返回的始终是旧记录，但 `last_fetched_at` 确实更新了。

**根因**：`list_logs()` 默认 limit=20，排序是倒序，新记录其实写进去了，只是 monitor 里用 `d[-3:]` 取的是最旧的 3 条。

**解决**：直接查全量 logs 确认，发现新记录都在。

## 四、本次对话复盘

### 4.1 问题识别

联调时发现 candidate_count 始终为 0，第一反应是 LLM 调用失败，但实际是更上游的规则过滤就没有产出候选。

### 4.2 根因分析

wechat-decrypt 是独立服务，它的消息类型字段用中文（`"文本"`、`"链接/文件"`），而 wx-still 的过滤逻辑是按英文写的。两个系统之间的接口契约没有对齐。

### 4.3 解决过程

1. 用 curl 直接查 wechat-decrypt `/api/history`，打印所有 type 值
2. 发现全是中文类型名
3. 修改 `_is_candidate` 和 `_is_valid` 支持中英文
4. 重启服务，重置 `last_fetched_at`，重新触发 collect
5. 直接用 Python 跑 pipeline 验证，确认 candidates 和 insights 都有产出

### 4.4 经验教训

集成第三方服务时，**字段值的格式（尤其是枚举值）必须以实际 API 响应为准**，不能假设。应该在写过滤逻辑之前先 curl 一下看真实数据。

### 4.5 预防措施

下次集成新数据源时，先写一个小脚本打印所有字段的实际值，再写过滤逻辑。

## 五、创建/修改的文件清单

- `server/insights.py` — 修复消息类型匹配，新增 `derive_strategy_from_feedback()`
- `server/main.py` — 配置迁移到 dotenv，`/feedback` 端点加策略转换
- `requirements.txt` — 新增 `python-dotenv>=1.0`
- `.gitignore` — 简化，改为忽略 `.env`
- 删除：`config.example.sh`、`scripts/extract-qa.py`、`scripts/merge-qa.py`、`scripts/write-feishu-doc.sh`
- 新增：`.env.example`

## 六、技术栈/技术决策

- **配置管理**：从 bash `config.sh` 迁移到 `python-dotenv`，更标准，IDE 友好
- **消息类型**：wechat-decrypt 用中文类型名，wx-still 现在同时支持中英文

## 七、下一步工作

1. **定时自动采集** — 加 APScheduler，不用手动 POST `/collect`
2. **UI 展示 insights** — 管理页面加 insights 列表，展示提取结果
3. **KnowWind 推送联调** — `pushed_count` 一直是 0，需要 KnowWind 服务在线
4. **`/feedback` UI** — 管理页面加反馈输入框

---

## 快速摘要（用于下次对话）

**完成：** 配置迁移到 dotenv、删旧脚本、feedback 策略转换、修复消息类型 bug，打通完整采集链路（wechat-decrypt → LLM 提取 → log）

**问题：** `_is_candidate` 用英文 `"text"` 过滤，但 wechat-decrypt 返回中文类型名 → 加 `_TEXT_TYPES` 集合支持中英文

**经验：** 集成第三方服务前先 curl 打印真实字段值，不要假设枚举值格式

**下一步：** 定时自动采集（APScheduler）；UI 加 insights 展示；KnowWind 推送联调

**文件：** server/insights.py, server/main.py, requirements.txt, .gitignore
