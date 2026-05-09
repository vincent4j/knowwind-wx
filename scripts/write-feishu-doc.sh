#!/usr/bin/env bash
# write-feishu-doc.sh
# 将 QA 写入飞书文档，支持：
#   - 追加模式（默认）：只追加今天新问题，不覆盖已有内容（保护手动修改）
#   - 跨天去重：调用 merge-qa.py 用 LLM 判断重复，用户确认后更新历史频次
#   - --force：全量替换当天块（慎用，会覆盖手动修改）
#
# 用法：
#   ./scripts/write-feishu-doc.sh [--date YYYY-MM-DD] [--force] [--dry-run]

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────────────────────────────
# 自动探测 lark-cli 路径（优先 PATH，其次 nvm 最新版本）
LARK_CLI=$(command -v lark-cli 2>/dev/null || ls "$HOME"/.nvm/versions/node/*/bin/lark-cli 2>/dev/null | sort -V | tail -1 || echo "")
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPTS_DIR/../config.sh"
FEISHU_DOC="$FEISHU_DOC_URL"

# ── 参数解析 ──────────────────────────────────────────────────────────────────
DATE=""
DRY_RUN=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)    DATE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force)   FORCE=true; shift ;;
    *)         echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$DATE" ]] && DATE=$(date +%Y-%m-%d)

echo "📅 写入日期：$DATE"
[[ "$DRY_RUN"  == "true" ]] && echo "🔍 Dry-run 模式，不实际写入"
[[ "$FORCE"    == "true" ]] && echo "⚡ --force 模式，将全量替换当天块"

# ── 检查依赖 ──────────────────────────────────────────────────────────────────
if [[ -z "$LARK_CLI" || ! -f "$LARK_CLI" ]]; then
  echo "❌ 找不到 lark-cli，请先安装：npm install -g @larksuite/cli" >&2
  echo "   安装后重新打开终端，或手动设置：export PATH=\$PATH:/path/to/lark-cli" >&2
  exit 1
fi

# ── 检查 QA JSON 文件（extract-qa.py 输出） ───────────────────────────────────
QA_JSON="$TMP_DIR/wx_qa_${DATE}.json"
QA_MD="$TMP_DIR/wx_qa_${DATE}.md"

if [[ ! -f "$QA_JSON" ]]; then
  echo "❌ QA JSON 文件不存在：$QA_JSON" >&2
  echo "   请先运行：python3 scripts/extract-qa.py --date $DATE" >&2
  exit 1
fi

echo "📄 QA JSON：$QA_JSON"
echo ""

[[ "$DRY_RUN" == "true" ]] && { echo "✅ Dry-run 完成"; exit 0; }

# ── 步骤 1：跨天去重 + 用户确认 ──────────────────────────────────────────────
echo "══════════════════════════════════════════════════════"
echo "步骤 1/4：跨天去重检查"
echo "══════════════════════════════════════════════════════"

FORCE_FLAG=""
[[ "$FORCE" == "true" ]] && FORCE_FLAG="--force"

# merge-qa.py 输出最后两行是 APPEND_PLAN=... 和 UPDATE_PLAN=...
MERGE_OUTPUT=$(python3 "$SCRIPTS_DIR/merge-qa.py" \
  --date "$DATE" \
  --qa-json "$QA_JSON" \
  $FORCE_FLAG)

echo "$MERGE_OUTPUT"

APPEND_PLAN=$(echo "$MERGE_OUTPUT" | grep "^APPEND_PLAN=" | cut -d= -f2-)
UPDATE_PLAN=$(echo "$MERGE_OUTPUT"  | grep "^UPDATE_PLAN="  | cut -d= -f2-)

if [[ -z "$APPEND_PLAN" || ! -f "$APPEND_PLAN" ]]; then
  echo "❌ 未找到追加计划文件" >&2; exit 1
fi

APPEND_COUNT=$(python3 -c "import json; print(len(json.load(open('$APPEND_PLAN'))))")
UPDATE_COUNT=$(python3 -c "import json; print(len(json.load(open('$UPDATE_PLAN'))))")

echo ""
echo "   新问题追加：$APPEND_COUNT 个"
echo "   历史问题更新频次：$UPDATE_COUNT 个"

# ── 步骤 2：更新历史问题频次 ──────────────────────────────────────────────────
if [[ "$UPDATE_COUNT" -gt 0 ]]; then
  echo ""
  echo "══════════════════════════════════════════════════════"
  echo "步骤 2/4：更新历史问题频次"
  echo "══════════════════════════════════════════════════════"

  python3 - <<PYEOF
import json, subprocess, re, sys
from pathlib import Path

update_plan = json.loads(Path("$UPDATE_PLAN").read_text())
lark_cli = "$LARK_CLI"
feishu_doc = "$FEISHU_DOC"
tmp_dir = Path("$TMP_DIR")

for item in update_plan:
    block_id = item["block_id"]
    title    = item["title"]
    new_occ  = item["new_occurrences"]
    new_dial = item["new_dialog_count"]
    date     = item["date"]
    q_num    = item["q_num"]

    if not block_id:
        print(f"⚠️  [{date} {q_num}] 无 block_id，跳过更新：{title[:30]}")
        continue

    # 拉取该块的当前内容（通过 fetch 整个文档后定位）
    # 策略：用 selection-by-title 定位到该 Q 块，替换频次行
    # 生成新的频次行
    new_freq_line = f"频次：出现 {new_occ} 次，累计 {new_dial} 条对话"

    # 拉取文档内容，找到该 Q 块的完整内容
    result = subprocess.run(
        [lark_cli, "docs", "+fetch",
         "--doc", feishu_doc,
         "--format", "pretty"],
        capture_output=True, text=True
    )
    doc = result.stdout

    # 找到该 Q 块的内容（从 ### Q{n}：{title} 到下一个 ### 或 ## 之间）
    q_header = f"### {q_num}：{title}"
    start = doc.find(q_header)
    if start == -1:
        print(f"⚠️  未找到块：{q_header[:40]}，跳过")
        continue

    # 找到下一个 ### 或 ## 的位置
    next_section = re.search(r'\n(#{2,3} )', doc[start + len(q_header):])
    if next_section:
        end = start + len(q_header) + next_section.start()
    else:
        end = len(doc)

    block_content = doc[start:end]

    # 替换频次行
    old_freq_pattern = re.compile(r'频次：出现 \d+ 次，累计 \d+ 条对话')
    if not old_freq_pattern.search(block_content):
        print(f"⚠️  未找到频次行：{q_header[:40]}，跳过")
        continue

    new_block_content = old_freq_pattern.sub(new_freq_line, block_content)

    # 写入临时文件
    tmp_file = tmp_dir / f"wx_qa_update_{date}_{q_num}.md"
    tmp_file.write_text(new_block_content, encoding="utf-8")

    # 用 replace_range 替换该块
    r = subprocess.run(
        [lark_cli, "docs", "+update",
         "--doc", feishu_doc,
         "--selection-by-title", f"### {q_num}：{title}",
         "--mode", "replace_range",
         "--markdown", f"@{tmp_file.name}"],
        capture_output=True, text=True,
        cwd=str(tmp_dir)
    )
    if '"ok": true' in r.stdout or '"success": true' in r.stdout:
        print(f"   ✅ [{date} {q_num}] 频次更新：{item['old_occurrences']} → {new_occ} 次，{item['old_dialog_count']} → {new_dial} 条对话")
    else:
        print(f"   ❌ [{date} {q_num}] 更新失败：{r.stdout[:100]}")

    tmp_file.unlink(missing_ok=True)

print("   历史频次更新完成")
PYEOF
fi

# ── 步骤 3：追加今天新问题 ────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "步骤 3/4：追加今天新问题"
echo "══════════════════════════════════════════════════════"

if [[ "$APPEND_COUNT" -eq 0 ]]; then
  echo "   今天没有新问题需要追加"
else
  # 用 Python 把 append_plan.json 渲染成 Markdown
  python3 - <<PYEOF
import json, re
from pathlib import Path

append_plan = json.loads(Path("$APPEND_PLAN").read_text())
date_str = "$DATE"
tmp_dir = Path("$TMP_DIR")

# 先拉取文档，确认今天的块是否已存在，以及已有多少个 Q
import subprocess
result = subprocess.run(
    ["$LARK_CLI", "docs", "+fetch",
     "--doc", "$FEISHU_DOC",
     "--scope", "outline",
     "--format", "json"],
    capture_output=True, text=True
)
outline_raw = result.stdout
try:
    idx = outline_raw.index('{')
    outline_data = json.loads(outline_raw[idx:])
    outline_content = outline_data['data']['document']['content']
except Exception:
    outline_content = ""

# 今天已有的 Q 标题
existing_titles = set()
for bid, title in re.findall(r'<h3[^>]*id="([^"]+)"[^>]*>(.*?)</h3>', outline_content):
    clean = re.sub(r'<[^>]+>', '', title).strip()
    existing_titles.add(clean)

# 今天已有的 Q 数量
today_h2_pattern = re.compile(rf'## {date_str}：(\d+) 个问题')
today_q_count = 0
for bid, title in re.findall(r'<h2[^>]*id="([^"]+)"[^>]*>(.*?)</h2>', outline_content):
    clean = re.sub(r'<[^>]+>', '', title).strip()
    m = today_h2_pattern.match(clean)
    if m:
        today_q_count = int(m.group(1))
        today_h2_id = bid
        break

# 过滤掉已存在的问题（同天追加时的去重）
new_qs = []
for q in append_plan:
    title = q.get("title", "")
    # 检查是否已存在（任意 Q 编号 + 该标题）
    already = any(title in existing for existing in existing_titles)
    if not already:
        new_qs.append(q)

if not new_qs:
    print("   今天所有问题已存在于文档中，无需追加")
    Path("$TMP_DIR/wx_qa_new_qs_count.txt").write_text("0")
    exit(0)

# 新 Q 的起始编号
start_num = today_q_count + 1
total_new = today_q_count + len(new_qs)

print(f"   今天已有 {today_q_count} 个问题，追加 {len(new_qs)} 个，共 {total_new} 个")

# 生成追加的 Markdown（只包含新问题，不含日期标题）
lines = []
for i, q in enumerate(new_qs, start_num):
    occ    = q.get("occurrences", 1)
    dialogs = q.get("dialog_count", 0)
    title  = q.get("title", "")
    answer = q.get("answer", "（群里暂无文字回复）")
    links  = q.get("links", [])

    lines.append(f"### Q{i}：{title}")
    lines.append("")
    lines.append(f"频次：出现 {occ} 次，累计 {dialogs} 条对话")
    lines.append("")
    lines.append(f"群里的回答：{answer}")
    lines.append("")
    if links:
        lines.append("资料：")
        for name, url in links:
            lines.append(f"- {name}：{url}")
        lines.append("")

append_md = Path("$TMP_DIR/wx_qa_append_${DATE}.md")
append_md.write_text("\n".join(lines), encoding="utf-8")
print(f"   追加内容写入：{append_md}")

# 保存新总数供后续更新标题用
Path("$TMP_DIR/wx_qa_new_qs_count.txt").write_text(str(total_new))
Path("$TMP_DIR/wx_qa_today_h2_title.txt").write_text(f"{date_str}：{today_q_count} 个问题")
PYEOF

  APPEND_MD="$TMP_DIR/wx_qa_append_${DATE}.md"
  NEW_COUNT_FILE="$TMP_DIR/wx_qa_new_qs_count.txt"

  if [[ -f "$APPEND_MD" ]]; then
    TODAY_H2_TITLE=$(cat "$TMP_DIR/wx_qa_today_h2_title.txt" 2>/dev/null || echo "")
    NEW_TOTAL=$(cat "$NEW_COUNT_FILE" 2>/dev/null || echo "0")

    if [[ -n "$TODAY_H2_TITLE" && "$NEW_TOTAL" -gt 0 ]]; then
      # 今天的块已存在 → 在块末尾（下一个 ## 之前）插入新问题
      echo "   今天块已存在，在末尾追加新问题..."
      cd "$TMP_DIR" && "$LARK_CLI" docs +update \
        --doc "$FEISHU_DOC" \
        --selection-by-title "## $TODAY_H2_TITLE" \
        --mode insert_after \
        --markdown "@wx_qa_append_${DATE}.md" 2>&1 | grep -E '"ok"|"message"' || true
    else
      # 今天的块不存在 → 在 2026-05-08 块之前插入整个今天的块
      echo "   今天块不存在，创建新块..."
      # 先生成完整的今天块（含标题）
      python3 - <<INNERPY
import json
from pathlib import Path

append_plan = json.loads(Path("$APPEND_PLAN").read_text())
date_str = "$DATE"
lines = []
lines.append(f"## {date_str}：{len(append_plan)} 个问题")
lines.append("")
for i, q in enumerate(append_plan, 1):
    occ     = q.get("occurrences", 1)
    dialogs = q.get("dialog_count", 0)
    title   = q.get("title", "")
    answer  = q.get("answer", "（群里暂无文字回复）")
    links   = q.get("links", [])
    lines.append(f"### Q{i}：{title}")
    lines.append("")
    lines.append(f"频次：出现 {occ} 次，累计 {dialogs} 条对话")
    lines.append("")
    lines.append(f"群里的回答：{answer}")
    lines.append("")
    if links:
        lines.append("资料：")
        for name, url in links:
            lines.append(f"- {name}：{url}")
        lines.append("")
Path("$TMP_DIR/wx_qa_full_${DATE}.md").write_text("\n".join(lines), encoding="utf-8")
INNERPY
      cd "$TMP_DIR" && "$LARK_CLI" docs +update \
        --doc "$FEISHU_DOC" \
        --selection-by-title "## $(cat "$TMP_DIR/wx_qa_prev_h2.txt" 2>/dev/null || echo '2026-05-08：12 个问题')" \
        --mode insert_before \
        --markdown "@wx_qa_full_${DATE}.md" 2>&1 | grep -E '"ok"|"message"' || true
    fi

    # 更新今天块的标题（问题数量）
    if [[ "$NEW_TOTAL" -gt 0 && -n "$TODAY_H2_TITLE" ]]; then
      NEW_H2_TITLE="${DATE}：${NEW_TOTAL} 个问题"
      echo "   更新标题：$TODAY_H2_TITLE → $NEW_H2_TITLE"
      echo "## $NEW_H2_TITLE" > "$TMP_DIR/wx_qa_h2_${DATE}.md"
      cd "$TMP_DIR" && "$LARK_CLI" docs +update \
        --doc "$FEISHU_DOC" \
        --selection-by-title "## $TODAY_H2_TITLE" \
        --mode replace_range \
        --markdown "@wx_qa_h2_${DATE}.md" 2>&1 | grep -E '"ok"|"message"' || true
    fi

    rm -f "$APPEND_MD" "$NEW_COUNT_FILE" \
          "$TMP_DIR/wx_qa_today_h2_title.txt" \
          "$TMP_DIR/wx_qa_h2_${DATE}.md" \
          "$TMP_DIR/wx_qa_full_${DATE}.md"
    echo "   ✅ 新问题追加完成"
  fi
fi

# ── 步骤 4：更新总目录 ────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "步骤 4/4：更新总目录"
echo "══════════════════════════════════════════════════════"

python3 - <<PYEOF
import json, re, subprocess
from pathlib import Path

lark_cli = "$LARK_CLI"
feishu_doc = "$FEISHU_DOC"
tmp_dir = Path("$TMP_DIR")
date_str = "$DATE"

# 拉取最新大纲
result = subprocess.run(
    [lark_cli, "docs", "+fetch",
     "--doc", feishu_doc,
     "--scope", "outline",
     "--format", "json"],
    capture_output=True, text=True
)
outline_raw = result.stdout
try:
    idx = outline_raw.index('{')
    outline_data = json.loads(outline_raw[idx:])
    outline_content = outline_data['data']['document']['content']
except Exception:
    print("⚠️  无法解析大纲，跳过总目录更新")
    exit(0)

doc_id = "QoaDdPxXho58h6xl9IVcYlVonNg"
base_url = f"https://nodewalk.feishu.cn/docx/{doc_id}"

# 拉取完整文档内容，找高频问题
result2 = subprocess.run(
    [lark_cli, "docs", "+fetch",
     "--doc", feishu_doc,
     "--format", "pretty"],
    capture_output=True, text=True
)
doc_content = result2.stdout

# 从文档中提取所有 Q 的频次（跨所有日期）
freq_pattern = re.compile(r'### (Q\d+)：(.+?)\n.*?频次：出现 (\d+) 次', re.DOTALL)
h3_ids = {}
for bid, title in re.findall(r'<h3[^>]*id="([^"]+)"[^>]*>(.*?)</h3>', outline_content):
    clean = re.sub(r'<[^>]+>', '', title).strip()
    h3_ids[clean] = bid

hot_qs = []
for m in freq_pattern.finditer(doc_content):
    q_num = m.group(1)
    title = m.group(2).strip()
    occ   = int(m.group(3))
    if occ >= 2:
        full_key = f"{q_num}：{title}"
        bid = h3_ids.get(full_key, "")
        url = f"{base_url}#{bid}" if bid else ""
        hot_qs.append((title, occ, url))

hot_qs.sort(key=lambda x: -x[1])

# 生成总目录
lines = ["## 📚 总目录", ""]
if hot_qs:
    lines.append("🔥 高频问题（出现 2 次以上，按频次倒序）")
    lines.append("")
    for title, occ, url in hot_qs:
        if url:
            lines.append(f"- [{title}（出现 {occ} 次）]({url})")
        else:
            lines.append(f"- {title}（出现 {occ} 次）")
    lines.append("")

toc_file = tmp_dir / f"wx_qa_toc_{date_str}.md"
toc_file.write_text("\n".join(lines), encoding="utf-8")

# 删除旧总目录，插入新的
r = subprocess.run(
    [lark_cli, "docs", "+update",
     "--doc", feishu_doc,
     "--selection-by-title", "## 📚 总目录",
     "--mode", "delete_range"],
    capture_output=True, text=True
)

# 找第一个日期块标题，在它之前插入总目录
first_h2 = None
for bid, title in re.findall(r'<h2[^>]*id="([^"]+)"[^>]*>(.*?)</h2>', outline_content):
    clean = re.sub(r'<[^>]+>', '', title).strip()
    if re.match(r'\d{4}-\d{2}-\d{2}', clean):
        first_h2 = clean
        break

if first_h2:
    subprocess.run(
        [lark_cli, "docs", "+update",
         "--doc", feishu_doc,
         "--selection-by-title", f"## {first_h2}",
         "--mode", "insert_before",
         "--markdown", f"@{toc_file.name}"],
        capture_output=True, text=True,
        cwd=str(tmp_dir)
    )
    print(f"   ✅ 总目录更新完成（{len(hot_qs)} 个高频问题）")
else:
    print("   ⚠️  未找到日期块，跳过总目录插入")

toc_file.unlink(missing_ok=True)
PYEOF

# ── 清理 ──────────────────────────────────────────────────────────────────────
echo ""
echo "🧹 清理临时文件..."
rm -f \
  "$TMP_DIR/wx_qa_export_${DATE}.json" \
  "$TMP_DIR/wx_qa_groups_${DATE}.json" \
  "$TMP_DIR/wx_qa_append_plan_${DATE}.json" \
  "$TMP_DIR/wx_qa_update_plan_${DATE}.json"

echo ""
echo "✅ 全部完成"
echo "   飞书文档：$FEISHU_DOC"
