#!/usr/bin/env python3
# extract-qa.py
# 从微信群消息中提取 QA，合并相似问题，计算频次和对话条数
# 用法：python3 scripts/extract-qa.py [--date YYYY-MM-DD]

import json
import re
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────────────────
import os
TMP_DIR = Path(os.environ.get("TMP_DIR", "/private/tmp"))

# 问题识别关键词
QUESTION_KEYWORDS = [
    "请问", "问下", "问一下", "想问", "怎么", "如何", "为什么", "为啥",
    "能不能", "有没有", "可以吗", "报错", "安装", "登录", "提交",
    "无法", "不显示", "不能", "失败", "错误", "问题", "#举手", "？", "?"
]

# 过滤关键词（命中则跳过）
FILTER_KEYWORDS = [
    "拍了拍", "撤回了", "[系统]", "加入了群聊", "邀请", "修改群名",
]

# 敏感话题关键词（问题内容命中则整条过滤）
SENSITIVE_KEYWORDS = [
    "科学上网", "梯子", "翻墙", "VPN", "vpn", "代理", "上科技",
    "机场", "节点", "clash", "Clash", "shadowsocks", "v2ray", "trojan",
]

# 纯表情/无意义短句（长度 <= 5 且不含问号）
MIN_QUESTION_LENGTH = int(os.environ.get("MIN_QUESTION_LENGTH", "8"))

# 15 分钟窗口（秒）
SESSION_WINDOW = int(os.environ.get("SESSION_WINDOW", "900"))

# 答案关联窗口（问题后 15 分钟内的回复）
ANSWER_WINDOW = int(os.environ.get("ANSWER_WINDOW", "900"))


def parse_args():
    parser = argparse.ArgumentParser(description="提取微信群 QA")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="处理日期，格式 YYYY-MM-DD（默认今天）")
    return parser.parse_args()


def load_messages(date_str: str) -> list[dict]:
    """加载指定日期的消息文件"""
    export_file = TMP_DIR / f"wx_qa_export_{date_str}.json"
    if not export_file.exists():
        print(f"❌ 消息文件不存在：{export_file}", file=sys.stderr)
        print("   请先运行：./scripts/export-wechat-groups.sh", file=sys.stderr)
        sys.exit(1)

    with open(export_file, encoding="utf-8") as f:
        messages = json.load(f)

    print(f"📂 加载消息：{len(messages)} 条（来自 {export_file}）")
    return messages


def is_valid_message(msg: dict) -> bool:
    """判断消息是否有效（排除系统消息、拍一拍、纯表情）"""
    msg_type = msg.get("type", "")
    content = msg.get("content", "")

    # 排除系统消息
    if msg_type == "系统":
        return False

    # 排除过滤关键词
    if any(kw in content for kw in FILTER_KEYWORDS):
        return False

    # 排除纯表情
    if msg_type == "表情":
        return False

    return True


def is_sensitive(content: str) -> bool:
    """判断消息是否涉及敏感话题（科学上网等）"""
    return any(kw in content for kw in SENSITIVE_KEYWORDS)


def is_question(msg: dict) -> bool:
    """判断消息是否为问题"""
    content = msg.get("content", "")
    msg_type = msg.get("type", "")

    # 只处理文本消息
    if msg_type not in ("文本",):
        return False

    # 过滤太短的消息（无上下文短句）
    if len(content.strip()) < MIN_QUESTION_LENGTH:
        return False

    # 过滤敏感话题
    if is_sensitive(content):
        return False

    # 命中问题关键词
    return any(kw in content for kw in QUESTION_KEYWORDS)


def extract_question_candidates(messages: list[dict]) -> list[dict]:
    """提取问题候选"""
    candidates = []
    for msg in messages:
        if not is_valid_message(msg):
            continue
        if is_question(msg):
            candidates.append(msg)
    print(f"🔍 问题候选：{len(candidates)} 条")
    return candidates


def find_answer_messages(question: dict, all_messages: list[dict]) -> list[dict]:
    """找到问题后 ANSWER_WINDOW 秒内的相关回复"""
    q_ts = question.get("timestamp", 0)
    q_idx = next((i for i, m in enumerate(all_messages) if m is question), -1)

    if q_idx == -1:
        return []

    answers = []
    for msg in all_messages[q_idx + 1:]:
        ts = msg.get("timestamp", 0)
        if ts - q_ts > ANSWER_WINDOW:
            break
        if is_valid_message(msg):
            answers.append(msg)

    return answers


def group_into_sessions(question: dict, all_messages: list[dict]) -> list[list[dict]]:
    """
    将同一问题的多次出现按 15 分钟窗口分组。
    返回 sessions 列表，每个 session 是一组相关消息。
    """
    # 找到所有与该问题相关的消息（问题本身 + 答案）
    q_ts = question.get("timestamp", 0)
    related = [question] + find_answer_messages(question, all_messages)

    # 按时间戳分组（15 分钟窗口）
    sessions = []
    current_session = []
    session_start = None

    for msg in sorted(related, key=lambda m: m.get("timestamp", 0)):
        ts = msg.get("timestamp", 0)
        if session_start is None or ts - session_start > SESSION_WINDOW:
            if current_session:
                sessions.append(current_session)
            current_session = [msg]
            session_start = ts
        else:
            current_session.append(msg)

    if current_session:
        sessions.append(current_session)

    return sessions


def summarize_question(content: str) -> str:
    """从消息内容中提取简短问题标题（截断到 50 字）"""
    # 去掉 @某人 前缀
    content = re.sub(r"@\S+\s*", "", content).strip()
    # 取第一行
    first_line = content.split("\n")[0].strip()
    # 截断
    if len(first_line) > 50:
        first_line = first_line[:47] + "..."
    return first_line


def merge_similar_questions(candidates: list[dict], all_messages: list[dict]) -> list[dict]:
    """
    合并相似问题，计算出现次数和累计对话条数。
    简单策略：关键词重叠度 > 50% 视为相似问题。
    """
    def keywords_of(text: str) -> set:
        # 提取中文词（2字以上）和英文词
        words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", text))
        return words

    merged = []

    for cand in candidates:
        content = cand.get("content", "")
        cand_kws = keywords_of(content)

        # 尝试合并到已有问题
        matched = None
        for existing in merged:
            existing_kws = keywords_of(existing["title"])
            if not cand_kws or not existing_kws:
                continue
            overlap = len(cand_kws & existing_kws) / max(len(cand_kws), len(existing_kws))
            if overlap >= 0.4:
                matched = existing
                break

        # 计算该候选的 sessions
        sessions = group_into_sessions(cand, all_messages)
        occurrence_count = len(sessions)
        dialog_count = sum(len(s) for s in sessions)
        first_ts = cand.get("timestamp", 0)

        if matched:
            # 合并到已有问题
            matched["occurrences"] += occurrence_count
            matched["dialog_count"] += dialog_count
            matched["first_ts"] = min(matched["first_ts"], first_ts)
            matched["raw_messages"].extend([cand])
        else:
            answer_msgs = find_answer_messages(cand, all_messages)
            # 过滤掉没有有效答案的问题
            if not has_valid_answer(answer_msgs):
                continue
            # 新问题
            merged.append({
                "title": summarize_question(content),
                "raw_content": content,
                "occurrences": occurrence_count,
                "dialog_count": dialog_count,
                "first_ts": first_ts,
                "raw_messages": [cand],
                "answer_messages": answer_msgs,
            })

    print(f"🔗 合并后问题：{len(merged)} 个（已过滤无答案和敏感话题）")
    return merged


def extract_urls(messages: list[dict]) -> list[str]:
    """从消息列表中提取 URL"""
    urls = []
    url_pattern = re.compile(r"https?://[^\s\u3000-\u9fff「」【】（）()，。！？]+")
    for msg in messages:
        content = msg.get("content", "")
        found = url_pattern.findall(content)
        urls.extend(found)
    # 去重，保留顺序
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
    return unique_urls


def has_valid_answer(answer_messages: list[dict]) -> bool:
    """判断是否有有效答案（至少 1 条 >= 10 字的文本回复，且不是敏感内容）"""
    for msg in answer_messages:
        if msg.get("type") == "文本":
            content = msg.get("content", "").strip()
            if len(content) >= 10 and not is_sensitive(content):
                return True
    return False


def extract_answer_texts(answer_messages: list[dict], max_count: int = 5) -> list[str]:
    """从答案消息中提取原始文本回复（不做 AI 总结，直接用群里的原话）"""
    texts = []
    for msg in answer_messages:
        if msg.get("type") == "文本":
            content = msg.get("content", "").strip()
            # 过滤太短的回复和敏感内容
            if len(content) >= 10 and not is_sensitive(content):
                # 去掉 @某人 前缀
                content = re.sub(r"@\S+\s*", "", content).strip()
                if content:
                    texts.append(content)
        if len(texts) >= max_count:
            break
    return texts


def build_keyword_index(sorted_qs: list[dict]) -> list[tuple[str, str]]:
    """
    为每个问题提取 2-3 个检索关键词，返回 [(关键词组, Q编号标题), ...]
    关键词取问题标题里的中文实词（2字以上），最多取前 3 个。
    """
    rows = []
    for i, q in enumerate(sorted_qs, 1):
        title = q["title"]
        # 提取中文实词（2字以上），排除常见虚词
        stopwords = {"怎么", "如何", "为什么", "可以", "能不能", "有没有", "是什么",
                     "需要", "一个", "这个", "那个", "什么", "问题", "还是", "或者"}
        words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9]{2,}", title)
        keywords = [w for w in words if w not in stopwords][:3]
        if keywords:
            rows.append((", ".join(keywords), f"Q{i}"))
    return rows


def render_markdown(questions: list[dict], date_str: str, groups_file: Path) -> str:
    """生成 Markdown 输出"""
    # 排序：出现次数降序，同频按最早时间升序
    sorted_qs = sorted(questions, key=lambda q: (-q["occurrences"], q["first_ts"]))

    lines = []
    lines.append(f"## {date_str}：{len(sorted_qs)} 个问题")
    lines.append("")

    # ── 高频问题（出现次数 >= 2，按频次倒序）────────────────────────────────
    hot_qs = [(i + 1, q) for i, q in enumerate(sorted_qs) if q["occurrences"] >= 2]
    if hot_qs:
        lines.append("**🔥 高频问题**")
        lines.append("")
        for q_num, q in hot_qs:
            lines.append(f"- {q['title']}（出现 {q['occurrences']} 次）")
        lines.append("")

    # ── 关键词速查表 ──────────────────────────────────────────────────────────
    kw_rows = build_keyword_index(sorted_qs)
    if kw_rows:
        lines.append("**🔍 关键词速查**")
        lines.append("")
        lines.append("| 搜索关键词 | 对应问题 |")
        lines.append("| --- | --- |")
        for kws, q_ref in kw_rows:
            lines.append(f"| {kws} | {q_ref} |")
        lines.append("")

    # ── 各问题详情 ────────────────────────────────────────────────────────────
    for i, q in enumerate(sorted_qs, 1):
        lines.append(f"### Q{i}：{q['title']}")
        lines.append("")
        lines.append(f"**频次：**出现 {q['occurrences']} 次，累计 {q['dialog_count']} 条对话")
        lines.append("")
        lines.append("**答案：**")
        answer_texts = extract_answer_texts(q.get("answer_messages", []))
        lines.append("\n\n".join(answer_texts))
        lines.append("")

        # 相关资源
        urls = extract_urls(q.get("answer_messages", []))
        if urls:
            lines.append("**相关资源：**")
            for url in urls[:5]:  # 最多 5 个
                lines.append(f"- {url}")
            lines.append("")

    return "\n".join(lines)


def main():
    args = parse_args()
    date_str = args.date

    print(f"📅 处理日期：{date_str}")
    print("")

    # 加载消息
    messages = load_messages(date_str)

    # 过滤有效消息
    valid_messages = [m for m in messages if is_valid_message(m)]
    print(f"✅ 有效消息：{len(valid_messages)} 条（过滤系统消息/拍一拍/表情后）")

    # 提取问题候选
    candidates = extract_question_candidates(valid_messages)

    # 合并相似问题
    questions = merge_similar_questions(candidates, valid_messages)

    # 生成 Markdown
    groups_file = TMP_DIR / f"wx_qa_groups_{date_str}.json"
    markdown = render_markdown(questions, date_str, groups_file)

    # 写入 Markdown 文件
    output_file = TMP_DIR / f"wx_qa_{date_str}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown)

    # 写入 JSON 文件（供 merge-qa.py 使用）
    json_file = TMP_DIR / f"wx_qa_{date_str}.json"
    # 排序：出现次数降序，同频按最早时间升序
    sorted_qs = sorted(questions, key=lambda q: (-q["occurrences"], q["first_ts"]))
    json_data = []
    for q in sorted_qs:
        answer_texts = extract_answer_texts(q.get("answer_messages", []))
        urls = extract_urls(q.get("answer_messages", []))
        json_data.append({
            "title":        q["title"],
            "occurrences":  q["occurrences"],
            "dialog_count": q["dialog_count"],
            "first_ts":     q["first_ts"],
            "answer":       "\n".join(answer_texts) if answer_texts else "",
            "links":        [[url, url] for url in urls[:5]],
        })
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ QA 提取完成")
    print(f"   Markdown：{output_file}")
    print(f"   JSON：{json_file}")
    print(f"   问题数量：{len(questions)} 个")

    return str(output_file)


if __name__ == "__main__":
    main()
