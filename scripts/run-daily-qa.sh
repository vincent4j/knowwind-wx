#!/usr/bin/env bash
# run-daily-qa.sh
# 微信群 QA 整理总入口：导出 → 提取 → 预览 → 确认 → 写入飞书
# 用法：./scripts/run-daily-qa.sh [--date YYYY-MM-DD] [--skip-export] [--dry-run]

set -euo pipefail

# ── 路径配置 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config.sh"

# ── 参数解析 ──────────────────────────────────────────────────────────────────
DATE=""
SKIP_EXPORT=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)        DATE="$2"; shift 2 ;;
    --skip-export) SKIP_EXPORT=true; shift ;;
    --dry-run)     DRY_RUN=true; shift ;;
    -h|--help)
      echo "用法：$0 [--date YYYY-MM-DD] [--skip-export] [--dry-run]"
      echo ""
      echo "  --date YYYY-MM-DD   指定处理日期（默认今天）"
      echo "  --skip-export       跳过导出步骤，直接使用已有的 JSON 文件"
      echo "  --dry-run           只预览，不写入飞书文档"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$DATE" ]]; then
  DATE=$(date +%Y-%m-%d)
fi

# ── 打印标题 ──────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════╗"
echo "║         微信群 QA 整理 · 每日流程                    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "📅 处理日期：$DATE"
[[ "$DRY_RUN" == "true" ]] && echo "🔍 Dry-run 模式：不写入飞书"
echo ""

# ── 步骤一：导出微信群消息 ────────────────────────────────────────────────────
if [[ "$SKIP_EXPORT" == "true" ]]; then
  echo "⏭️  跳过导出步骤（--skip-export）"
  EXPORT_FILE="$TMP_DIR/wx_qa_export_${DATE}.json"
  if [[ ! -f "$EXPORT_FILE" ]]; then
    echo "❌ 找不到已有导出文件：$EXPORT_FILE" >&2
    exit 1
  fi
  echo "   使用已有文件：$EXPORT_FILE"
else
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "步骤 1/3：导出微信群消息"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  bash "$SCRIPT_DIR/export-wechat-groups.sh" --date "$DATE"
fi

echo ""

# ── 步骤二：提取 QA ───────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 2/3：提取 QA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPT_DIR/extract-qa.py" --date "$DATE"

echo ""

# ── 步骤三：预览 ─────────────────────────────────────────────────────────────
QA_FILE="$TMP_DIR/wx_qa_${DATE}.md"
GROUPS_FILE="$TMP_DIR/wx_qa_groups_${DATE}.json"

if [[ ! -f "$QA_FILE" ]]; then
  echo "❌ QA 文件未生成：$QA_FILE" >&2
  exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "步骤 3/3：预览（写入前确认）"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 统计信息
python3 - <<PYEOF
import json, re
from pathlib import Path

qa_file = Path("$QA_FILE")
groups_file = Path("$GROUPS_FILE")

content = qa_file.read_text(encoding="utf-8")

# 群数
group_count = 0
if groups_file.exists():
    groups = json.loads(groups_file.read_text(encoding="utf-8"))
    group_count = len(groups)
    group_names = [g["chat"] for g in groups]
else:
    group_names = []

# 问题数
q_count = len(re.findall(r"^### Q\d+：", content, re.MULTILINE))

# 消息时间范围（从第一行标题提取）
header_match = re.search(r"## (\d{4}-\d{2}-\d{2})：(\d+) 个问题", content)
date_str = header_match.group(1) if header_match else "$DATE"

print(f"📊 本次写入预览")
print(f"   日期：{date_str}")
print(f"   覆盖群数：{group_count} 个")
if group_names:
    for name in group_names:
        print(f"     · {name}")
print(f"   问题数量：{q_count} 个")
print(f"   文件大小：{qa_file.stat().st_size} 字节")
print()

# 前 3 个 QA 样例
sections = re.split(r"(?=^### Q\d+：)", content, flags=re.MULTILINE)
qa_sections = [s for s in sections if s.startswith("### Q")]

print("─" * 54)
print("前 3 个 QA 样例：")
print("─" * 54)
for section in qa_sections[:3]:
    # 只显示标题和频次行
    lines = section.strip().split("\n")
    for line in lines[:4]:
        if line.strip():
            print(line)
    print()
PYEOF

echo ""
echo "📄 完整 QA 文件：$QA_FILE"
echo "🔗 目标飞书文档：$FEISHU_DOC_URL"
echo ""

# ── Dry-run 模式 ──────────────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "true" ]]; then
  echo "✅ Dry-run 完成，未写入飞书"
  exit 0
fi

# ── 用户确认 ──────────────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -r -p "确认写入飞书文档？[y/N] " CONFIRM
echo ""

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "⏹️  已取消，未写入飞书"
  echo "   QA 文件保留在：$QA_FILE"
  exit 0
fi

# ── 写入飞书 ──────────────────────────────────────────────────────────────────
bash "$SCRIPT_DIR/write-feishu-doc.sh" --date "$DATE"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ 全部完成！                                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "   飞书文档：$FEISHU_DOC_URL"
