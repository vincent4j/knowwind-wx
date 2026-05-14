# 经验教训索引

本文件记录每次工作的关键经验教训，便于快速查找和回顾。

---

## 2026-05-14 - 项目文档与架构整理
- **任务：** 清理旧 CLI 架构残留（agent/ 目录），重写/更新全部文档使其与 FastAPI 架构一致
- **关键经验：**
  - 架构迁移后应立刻同步更新文档，不要推迟——技术债积累后整理成本更高
  - 删除代码前检查 shell 脚本（install.sh 等）中对 Python 文件的直接引用，不只是 `import`
  - install.sh 是用户安装的唯一真相，README 的安装章节必须与其保持一致
- **详见：** [worklog/2026-05-14-项目文档与架构整理.md](worklog/2026-05-14-项目文档与架构整理.md)

## 2026-05-09 - FastAPI 后台服务与 LLM 提取流水线（联调）
- **任务：** 配置迁移、删旧脚本、feedback 策略转换、真实数据联调
- **关键经验：**
  - 集成第三方服务时，枚举字段值必须以实际 API 响应为准（curl 验证），不能假设格式
  - 调试 pipeline 时，先隔离每一层（规则过滤 → LLM → 推送），逐层确认产出
- **详见：** [worklog/2026-05-09-FastAPI后台服务与LLM提取流水线.md](worklog/2026-05-09-FastAPI后台服务与LLM提取流水线.md)

## 2026-05-09 - FastAPI 后台服务与 LLM 提取流水线
- **任务：** 将 wx-still 改造为 KnowWind 插件服务（FastAPI + SQLite + Vue + LLM 提取）
- **关键经验：**
  - 集成第三方 HTTP 服务前必须验证实际端点（读源码或 curl 测试），不能只凭 README 假设
  - macOS PEP 668 禁止全局 pip，统一用 `uv venv + uv pip install`
- **详见：** [worklog/2026-05-09-FastAPI后台服务与LLM提取流水线.md](worklog/2026-05-09-FastAPI后台服务与LLM提取流水线.md)
