# 经验教训索引

本文件记录每次工作的关键经验教训，便于快速查找和回顾。

---

## 2026-05-09 - FastAPI 后台服务与 LLM 提取流水线
- **任务：** 将 wx-still 改造为 KnowWind 插件服务（FastAPI + SQLite + Vue + LLM 提取）
- **关键经验：**
  - 集成第三方 HTTP 服务前必须验证实际端点（读源码或 curl 测试），不能只凭 README 假设
  - macOS PEP 668 禁止全局 pip，统一用 `uv venv + uv pip install`
- **详见：** [worklog/2026-05-09-FastAPI后台服务与LLM提取流水线.md](worklog/2026-05-09-FastAPI后台服务与LLM提取流水线.md)
