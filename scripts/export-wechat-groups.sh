#!/usr/bin/env bash
# export-wechat-groups.sh
# 调用 wx-cli，导出目标微信群消息到 /private/tmp
# 用法：./scripts/export-wechat-groups.sh [--date YYYY-MM-DD]

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config.sh"

WX="$WX_CLI_PATH"
# 将逗号分隔的关键词字符串转为数组
IFS=',' read -ra GROUP_KEYWORDS <<< "$GROUP_KEYWORDS"

# ── 参数解析 ──────────────────────────────────────────────────────────────────
DATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --date) DATE="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$DATE" ]]; then
  DATE=$(date +%Y-%m-%d)
fi

echo "📅 导出日期：$DATE"

# ── 检查 wx-cli ───────────────────────────────────────────────────────────────
if [[ ! -f "$WX" ]]; then
  echo "❌ wx-cli 不存在：$WX" >&2
  echo "请先安装 wx-cli：cd /private/tmp/wx-cli-check && npm install @jackwener/wx-cli" >&2
  exit 1
fi

# ── 输出文件路径 ──────────────────────────────────────────────────────────────
GROUPS_FILE="$TMP_DIR/wx_qa_groups_${DATE}.json"
EXPORT_FILE="$TMP_DIR/wx_qa_export_${DATE}.json"

# ── 获取所有 sessions ─────────────────────────────────────────────────────────
echo "🔍 获取微信群列表..."
ALL_SESSIONS=$("$WX" sessions --json 2>/dev/null) || {
  echo "❌ wx sessions 失败，请确认 daemon 正在运行" >&2
  echo "   检查：cat ~/.wx-cli/daemon.log" >&2
  exit 1
}

# ── 过滤目标群 ────────────────────────────────────────────────────────────────
echo "🔎 过滤目标群（关键词：${GROUP_KEYWORDS[*]}）..."

python3 - <<PYEOF
import json, sys

sessions = json.loads('''$ALL_SESSIONS''')
keywords = ["超级 AI 大航海", "5月航海"]

target_groups = []
for s in sessions:
    chat = s.get("chat", "")
    if any(kw in chat for kw in keywords) and s.get("chat_type") == "group":
        target_groups.append(s)

print(f"找到 {len(target_groups)} 个目标群：")
for g in target_groups:
    print(f"  - {g['chat']} ({g['username']})")

with open("$GROUPS_FILE", "w", encoding="utf-8") as f:
    json.dump(target_groups, f, ensure_ascii=False, indent=2)
PYEOF

# ── 读取目标群列表 ────────────────────────────────────────────────────────────
if [[ ! -f "$GROUPS_FILE" ]]; then
  echo "❌ 群列表文件未生成" >&2
  exit 1
fi

GROUP_COUNT=$(python3 -c "import json; print(len(json.load(open('$GROUPS_FILE'))))")
if [[ "$GROUP_COUNT" -eq 0 ]]; then
  echo "⚠️  未找到目标群，请检查关键词或微信登录状态" >&2
  exit 1
fi

# ── 导出每个群的消息 ──────────────────────────────────────────────────────────
echo ""
echo "📥 开始导出群消息（日期：$DATE）..."

python3 - <<PYEOF
import json, subprocess, sys
from datetime import datetime

groups = json.load(open("$GROUPS_FILE", encoding="utf-8"))
wx_bin = "$WX"
date_str = "$DATE"
export_file = "$EXPORT_FILE"

all_messages = []
stats = []

for g in groups:
    chat_name = g["chat"]
    username = g["username"]
    print(f"  导出：{chat_name} ...", flush=True)

    try:
        result = subprocess.run(
            [wx_bin, "history", username, "--json", "--date", date_str],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"    ⚠️  导出失败：{result.stderr.strip()}", flush=True)
            continue

        messages = json.loads(result.stdout)
        # 给每条消息加上群名
        for m in messages:
            m["group"] = chat_name

        all_messages.extend(messages)
        stats.append({"chat": chat_name, "count": len(messages)})
        print(f"    ✅ {len(messages)} 条消息", flush=True)

    except subprocess.TimeoutExpired:
        print(f"    ⚠️  超时，跳过", flush=True)
    except json.JSONDecodeError as e:
        print(f"    ⚠️  JSON 解析失败：{e}", flush=True)

# 写入合并文件
with open(export_file, "w", encoding="utf-8") as f:
    json.dump(all_messages, f, ensure_ascii=False, indent=2)

print(f"\n✅ 导出完成：共 {len(all_messages)} 条消息，来自 {len(stats)} 个群")
print(f"   输出文件：{export_file}")
PYEOF

echo ""
echo "✅ 导出完成"
echo "   群列表：$GROUPS_FILE"
echo "   消息数据：$EXPORT_FILE"
