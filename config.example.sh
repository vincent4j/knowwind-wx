#!/usr/bin/env bash
# config.sh — 项目配置文件
# 复制本项目后，只需修改这个文件，其他脚本无需改动。
#
# 用法：source "$(dirname "$0")/../config.sh"（在脚本开头引入）

# ── 必须配置（换人就要改）────────────────────────────────────────────────────

# 飞书文档完整 URL
FEISHU_DOC_URL="https://your-tenant.feishu.cn/docx/YOUR_DOC_ID"

# wechat-decrypt 服务地址
# 启动方式：cd /path/to/wechat-decrypt && sudo ./find_all_keys_macos && python3 main.py
WECHAT_DECRYPT_URL="http://localhost:5678"

# 目标微信群关键词（逗号分隔，群名包含任意一个即纳入）
GROUP_KEYWORDS="你的群关键词1,你的群关键词2"

# ── 可选配置（有默认值，一般不需要改）───────────────────────────────────────

# 临时文件目录
TMP_DIR="${TMP_DIR:-/private/tmp}"

# 同一问题的消息合并时间窗口（秒，默认 15 分钟）
SESSION_WINDOW="${SESSION_WINDOW:-900}"

# 答案关联到问题的时间窗口（秒，默认 15 分钟）
ANSWER_WINDOW="${ANSWER_WINDOW:-900}"

# 有效问题的最短字符数
MIN_QUESTION_LENGTH="${MIN_QUESTION_LENGTH:-8}"

# LLM 模型（跨天去重用）
ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-opus-4-5}"

# ── 自动推导（不需要手动改）──────────────────────────────────────────────────

# 从 URL 中提取文档 ID
FEISHU_DOC_ID="${FEISHU_DOC_URL##*/docx/}"

# 导出所有配置变量，使 Python 子进程可以读取
export FEISHU_DOC_URL FEISHU_DOC_ID WECHAT_DECRYPT_URL GROUP_KEYWORDS
export TMP_DIR SESSION_WINDOW ANSWER_WINDOW MIN_QUESTION_LENGTH ANTHROPIC_MODEL
