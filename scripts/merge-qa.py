#!/usr/bin/env python3
# merge-qa.py
# 将今天新提取的 QA 与飞书文档中的历史问题做跨天去重：
#   1. 从飞书文档拉取所有历史问题标题
#   2. 调用 LLM 判断今天哪些问题与历史问题是同一个
#   3. 交互式让用户确认
#   4. 输出两个文件：
#      - append_plan.json  → 需要追加到今天块的新问题
#      - update_plan.json  → 需要更新频次的历史问题（block_id + 新频次/对话数）
#
# 用法：python3 scripts/merge-qa.py --date YYYY-MM-DD --qa-json /path/to/qa.json
#       --doc-content /path/to/doc_content.txt [--force]

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TMP_DIR = Path(os.environ.get("TMP_DIR", "/private/tmp"))
def find_lark_cli() -> Path:
    """自动探测 lark-cli 路径"""
    import shutil
    # 优先 PATH
    p = shutil.which("lark-cli")
    if p:
        return Path(p)
    # 其次 nvm 最新版本
    nvm_dir = Path.home() / ".nvm/versions/node"
    if nvm_dir.exists():
        candidates = sorted(nvm_dir.glob("*/bin/lark-cli"))
        if candidates:
            return candidates[-1]
    raise FileNotFoundError(
        "找不到 lark-cli，请先安装：npm install -g @larksuite/cli"
    )

LARK_CLI = find_lark_cli()
FEISHU_DOC = os.environ.get("FEISHU_DOC_URL", "")
if not FEISHU_DOC:
    raise RuntimeError("未设置 FEISHU_DOC_URL 环境变量，请先 source config.sh")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--qa-json", required=True, help="今天提取的 QA JSON 文件路径")
    p.add_argument("--force", action="store_true", help="跳过去重，全量写入")
    return p.parse_args()


# ── 从飞书文档拉取历史问题 ────────────────────────────────────────────────────

def fetch_doc_content() -> str:
    """拉取飞书文档完整内容（pretty 格式）"""
    result = subprocess.run(
        [str(LARK_CLI), "docs", "+fetch",
         "--doc", FEISHU_DOC,
         "--format", "pretty"],
        capture_output=True, text=True
    )
    return result.stdout


def parse_existing_questions(doc_content: str) -> list[dict]:
    """
    从文档内容中解析所有历史问题。
    返回：[{date, q_num, title, occurrences, dialog_count, block_id}, ...]
    """
    questions = []

    # 先从 outline 拿 block_id（需要单独拉）
    outline_result = subprocess.run(
        [str(LARK_CLI), "docs", "+fetch",
         "--doc", FEISHU_DOC,
         "--scope", "outline",
         "--format", "json"],
        capture_output=True, text=True
    )
    outline_raw = outline_result.stdout
    try:
        idx = outline_raw.index('{')
        outline_data = json.loads(outline_raw[idx:])
        outline_content = outline_data['data']['document']['content']
    except Exception:
        outline_content = ""

    # block_id 映射：标题文字 → block_id
    h3_ids = {}
    for bid, title in re.findall(r'<h3[^>]*id="([^"]+)"[^>]*>(.*?)</h3>', outline_content):
        clean = re.sub(r'<[^>]+>', '', title).strip()
        h3_ids[clean] = bid

    # 从 pretty 内容解析每个 Q 块
    # 格式：### Q{n}：{title}\n\n频次：出现 {occ} 次，累计 {dialogs} 条对话
    current_date = None
    date_pattern = re.compile(r'^## (\d{4}-\d{2}-\d{2})：')
    q_pattern = re.compile(r'^### (Q\d+)：(.+)')
    freq_pattern = re.compile(r'频次：出现 (\d+) 次，累计 (\d+) 条对话')

    lines = doc_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]

        # 检测日期标题
        dm = date_pattern.match(line)
        if dm:
            current_date = dm.group(1)
            i += 1
            continue

        # 检测 Q 标题
        qm = q_pattern.match(line)
        if qm and current_date:
            q_num = qm.group(1)
            title = qm.group(2).strip()
            occ = 1
            dialogs = 0

            # 向后找频次行（最多找 5 行）
            for j in range(i + 1, min(i + 6, len(lines))):
                fm = freq_pattern.search(lines[j])
                if fm:
                    occ = int(fm.group(1))
                    dialogs = int(fm.group(2))
                    break

            # 查找 block_id
            full_key = f"{q_num}：{title}"
            block_id = h3_ids.get(full_key, "")

            questions.append({
                "date": current_date,
                "q_num": q_num,
                "title": title,
                "occurrences": occ,
                "dialog_count": dialogs,
                "block_id": block_id,
            })

        i += 1

    return questions


# ── LLM 去重判断 ──────────────────────────────────────────────────────────────

def llm_dedup(today_titles: list[str], history_questions: list[dict]) -> list[dict]:
    """
    调用 claude CLI 判断今天的问题是否与历史问题重复。
    返回候选对列表：[{today_idx, history_idx, reason, confidence}, ...]
    """
    if not history_questions:
        return []

    history_lines = "\n".join(
        f"[{q['date']} {q['q_num']}] {q['title']}"
        for q in history_questions
    )
    today_lines = "\n".join(
        f"[今天 Q{i+1}] {t}"
        for i, t in enumerate(today_titles)
    )

    prompt = f"""你是一个问题去重助手。请判断"今天的问题"中，哪些与"历史问题"是同一个问题（语义相同，即使措辞不同）。

历史问题：
{history_lines}

今天的问题：
{today_lines}

请以 JSON 数组返回疑似重复的配对，格式：
[
  {{
    "today_label": "今天 Q1",
    "history_label": "2026-05-08 Q3",
    "today_title": "今天问题的标题",
    "history_title": "历史问题的标题",
    "confidence": "high/medium/low",
    "reason": "一句话说明为什么认为是同一个问题"
  }}
]

如果没有重复，返回空数组 []。只返回 JSON，不要其他文字。"""

    # 尝试调用 claude CLI
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
    except FileNotFoundError:
        # claude CLI 不可用，尝试用 python 调用 anthropic SDK
        try:
            import anthropic
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5"),
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            output = msg.content[0].text.strip()
        except Exception as e:
            print(f"⚠️  LLM 调用失败：{e}，跳过去重检查", file=sys.stderr)
            return []

    # 解析 JSON
    try:
        # 提取 JSON 数组
        json_match = re.search(r'\[.*\]', output, re.DOTALL)
        if json_match:
            pairs = json.loads(json_match.group())
            return pairs
    except Exception as e:
        print(f"⚠️  LLM 返回解析失败：{e}", file=sys.stderr)
        print(f"   原始输出：{output[:200]}", file=sys.stderr)

    return []


# ── 用户交互确认 ──────────────────────────────────────────────────────────────

def confirm_duplicates(
    pairs: list[dict],
    today_questions: list[dict],
    history_questions: list[dict]
) -> tuple[list[int], list[dict]]:
    """
    交互式确认哪些是真正的重复。
    返回：
      - skip_today_indices: 今天问题中需要跳过（不追加）的索引列表
      - update_items: 需要更新历史块的列表 [{block_id, title, add_occ, add_dialogs}, ...]
    """
    skip_today_indices = []
    update_items = []

    if not pairs:
        print("✅ LLM 未发现跨天重复问题")
        return skip_today_indices, update_items

    print(f"\n🔍 LLM 发现 {len(pairs)} 个疑似跨天重复问题，请逐一确认：")
    print("─" * 60)

    for pair in pairs:
        today_label = pair.get("today_label", "")
        history_label = pair.get("history_label", "")
        today_title = pair.get("today_title", "")
        history_title = pair.get("history_title", "")
        confidence = pair.get("confidence", "")
        reason = pair.get("reason", "")

        # 找到今天问题的索引
        today_idx = None
        for i, q in enumerate(today_questions):
            label = f"今天 Q{i+1}"
            if label == today_label or today_title in q.get("title", ""):
                today_idx = i
                break

        # 找到历史问题
        history_q = None
        for q in history_questions:
            label = f"{q['date']} {q['q_num']}"
            if label == history_label or history_title in q.get("title", ""):
                history_q = q
                break

        if today_idx is None or history_q is None:
            continue

        today_q = today_questions[today_idx]

        print(f"\n今天：{today_title or today_q['title']}")
        print(f"历史：[{history_q['date']} {history_q['q_num']}] {history_q['title']}")
        print(f"置信度：{confidence}  理由：{reason}")
        print(f"今天频次：{today_q['occurrences']} 次，{today_q['dialog_count']} 条对话")
        print(f"历史频次：{history_q['occurrences']} 次，{history_q['dialog_count']} 条对话")

        while True:
            ans = input("是同一个问题吗？[y=是，n=否，s=跳过] ").strip().lower()
            if ans in ("y", "n", "s"):
                break

        if ans == "y":
            skip_today_indices.append(today_idx)
            update_items.append({
                "block_id": history_q["block_id"],
                "date": history_q["date"],
                "q_num": history_q["q_num"],
                "title": history_q["title"],
                "old_occurrences": history_q["occurrences"],
                "old_dialog_count": history_q["dialog_count"],
                "add_occurrences": today_q["occurrences"],
                "add_dialog_count": today_q["dialog_count"],
                "new_occurrences": history_q["occurrences"] + today_q["occurrences"],
                "new_dialog_count": history_q["dialog_count"] + today_q["dialog_count"],
            })
            print(f"   ✅ 标记为重复，将更新历史块频次：{history_q['occurrences']} → {history_q['occurrences'] + today_q['occurrences']} 次")
        elif ans == "n":
            print("   ➡️  标记为不同问题，今天正常追加")
        else:
            print("   ⏭️  跳过，今天正常追加")

    print("─" * 60)
    return skip_today_indices, update_items


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # 加载今天的 QA JSON
    qa_json_path = Path(args.qa_json)
    if not qa_json_path.exists():
        print(f"❌ QA JSON 文件不存在：{qa_json_path}", file=sys.stderr)
        sys.exit(1)

    today_questions = json.loads(qa_json_path.read_text(encoding="utf-8"))
    print(f"📋 今天新提取问题：{len(today_questions)} 个")

    # --force 模式：跳过去重，全部追加
    if args.force:
        print("⚡ --force 模式，跳过去重检查")
        append_plan = today_questions
        update_plan = []
    else:
        # 拉取飞书文档内容
        print("📥 拉取飞书文档历史问题...")
        doc_content = fetch_doc_content()
        history_questions = parse_existing_questions(doc_content)

        # 过滤掉今天已有的问题（同一天的追加逻辑由 write-feishu-doc.sh 处理）
        history_questions = [q for q in history_questions if q["date"] != args.date]
        print(f"   历史问题（非今天）：{len(history_questions)} 个")

        if not history_questions:
            print("✅ 无历史问题，跳过去重")
            append_plan = today_questions
            update_plan = []
        else:
            # LLM 去重
            today_titles = [q["title"] for q in today_questions]
            print("🤖 调用 LLM 判断跨天重复...")
            pairs = llm_dedup(today_titles, history_questions)

            # 用户确认
            skip_indices, update_items = confirm_duplicates(
                pairs, today_questions, history_questions
            )

            # 生成追加计划（排除被标记为重复的）
            append_plan = [
                q for i, q in enumerate(today_questions)
                if i not in skip_indices
            ]
            update_plan = update_items

    # 写出计划文件
    append_plan_path = TMP_DIR / f"wx_qa_append_plan_{args.date}.json"
    update_plan_path = TMP_DIR / f"wx_qa_update_plan_{args.date}.json"

    append_plan_path.write_text(
        json.dumps(append_plan, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    update_plan_path.write_text(
        json.dumps(update_plan, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n📤 追加计划：{len(append_plan)} 个新问题 → {append_plan_path}")
    print(f"📝 更新计划：{len(update_plan)} 个历史问题需更新频次 → {update_plan_path}")

    # 输出供 shell 脚本读取
    print(f"APPEND_PLAN={append_plan_path}")
    print(f"UPDATE_PLAN={update_plan_path}")


if __name__ == "__main__":
    main()
