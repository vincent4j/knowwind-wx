"""
insights.py — 规则粗过滤 + LLM 精提取 + 推送 KnowWind
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent

load_dotenv(ROOT / ".env")

MIN_QUESTION_LENGTH = int(os.environ.get("MIN_QUESTION_LENGTH", "8"))
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5")

QUESTION_KEYWORDS = [
    "请问", "问下", "问一下", "想问", "怎么", "如何", "为什么", "为啥",
    "能不能", "有没有", "可以吗", "报错", "安装", "登录", "提交",
    "无法", "不显示", "不能", "失败", "错误", "问题", "#举手", "？", "?",
]

FILTER_KEYWORDS = [
    "拍了拍", "撤回了", "加入了群聊", "邀请", "修改群名",
]

SENSITIVE_KEYWORDS = [
    "科学上网", "梯子", "翻墙", "VPN", "vpn", "代理", "上科技",
    "机场", "节点", "clash", "Clash", "shadowsocks", "v2ray", "trojan",
]

STRATEGY_TEMPLATES = {
    "技术问答群": "这是一个技术问答群，重点关注有明确答案的技术问题，优先提取操作步骤清晰、可复用的问答。",
    "资讯分享群": "这是一个资讯分享群，重点关注有价值的行业资讯、工具推荐、经验分享。",
    "通用群": "这是一个通用讨论群，提取有价值的知识、经验分享和问答内容。",
}


# ── 规则过滤 ──────────────────────────────────────────────────────────────────

def _is_valid(msg: dict) -> bool:
    msg_type = (msg.get("type") or "").lower()
    content = msg.get("content") or ""
    if msg_type in ("system", "emoji"):
        return False
    if any(kw in content for kw in FILTER_KEYWORDS):
        return False
    return True


def _is_candidate(msg: dict) -> bool:
    msg_type = (msg.get("type") or "").lower()
    content = msg.get("content") or ""
    if msg_type != "text":
        return False
    if len(content.strip()) < MIN_QUESTION_LENGTH:
        return False
    return any(kw in content for kw in QUESTION_KEYWORDS)


def _is_sensitive(text: str) -> bool:
    return any(kw in text for kw in SENSITIVE_KEYWORDS)


def filter_candidates(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (valid_messages, candidate_messages)"""
    valid = [m for m in messages if _is_valid(m)]
    candidates = [m for m in valid if _is_candidate(m)]
    return valid, candidates


# ── LLM 提取 ─────────────────────────────────────────────────────────────────

def _format_messages_for_llm(valid_msgs: list[dict], candidates: list[dict]) -> str:
    candidate_ids = {id(m) for m in candidates}
    lines = []
    for msg in valid_msgs:
        ts = msg.get("timestamp", 0)
        time_str = datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "??"
        msg_type = (msg.get("type") or "text").lower()
        content = (msg.get("content") or "").replace("\n", " ").strip()
        if not content:
            continue
        prefix = "★" if id(msg) in candidate_ids else " "
        lines.append(f"{prefix} [{time_str}][{msg_type}] {content}")
    return "\n".join(lines)


def _build_prompt(
    valid_msgs: list[dict],
    candidates: list[dict],
    strategy_label: str | None,
    strategy_extra: str | None,
    strategy_feedback: str | None,
) -> str:
    template = STRATEGY_TEMPLATES.get(strategy_label or "", STRATEGY_TEMPLATES["通用群"])

    parts = ["你是一个微信群消息整理助手。\n"]
    parts.append(f"## 群策略\n{template}")
    if strategy_extra and strategy_extra.strip():
        parts.append(f"\n补充说明：{strategy_extra.strip()}")
    if strategy_feedback and strategy_feedback.strip():
        parts.append(f"\n## 历史反馈\n{strategy_feedback.strip()}")

    parts.append("""
## 任务
从下方微信群消息中提取有价值的内容。★ 标注的是候选消息，其余是上下文。

只提取有完整答案的问答、有价值的资讯或经验分享。敏感话题（翻墙/VPN 等）全部跳过。
发言人信息已脱敏，不要编造人名。

请输出 JSON 数组，每条格式如下（无其他文字）：
[
  {
    "type": "qa",
    "title": "简短标题（20字以内）",
    "content": "完整内容（含问题和答案）",
    "score": 85,
    "score_reason": "答案完整，有可操作步骤",
    "occurred_at": 1746700800
  }
]

如无有价值内容，返回 []。

## 消息列表
""")
    parts.append(_format_messages_for_llm(valid_msgs, candidates))
    return "\n".join(parts)


def _parse_llm_json(text: str) -> list[dict] | None:
    text = text.strip()
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _call_claude_cli(prompt: str) -> list[dict] | None:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_llm_json(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _call_anthropic_sdk(prompt: str) -> list[dict] | None:
    try:
        import anthropic  # optional dependency
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_llm_json(response.content[0].text)
    except Exception:
        pass
    return None


def _rule_based_fallback(candidates: list[dict]) -> list[dict]:
    insights = []
    for msg in candidates:
        content = (msg.get("content") or "").strip()
        title = content[:40] + ("…" if len(content) > 40 else "")
        insights.append({
            "type": "qa",
            "title": title,
            "content": content,
            "score": 50,
            "score_reason": "规则匹配（无 LLM）",
            "occurred_at": msg.get("timestamp", 0),
        })
    return insights


def extract_insights(
    messages: list[dict],
    strategy_label: str | None = None,
    strategy_extra: str | None = None,
    strategy_feedback: str | None = None,
) -> tuple[list[dict], int]:
    """
    返回 (insights, candidate_count)。
    insights 已过滤敏感话题。
    """
    valid_msgs, candidates = filter_candidates(messages)

    if not candidates:
        return [], 0

    prompt = _build_prompt(valid_msgs, candidates, strategy_label, strategy_extra, strategy_feedback)

    insights = _call_claude_cli(prompt)
    if insights is None:
        insights = _call_anthropic_sdk(prompt)
    if insights is None:
        insights = _rule_based_fallback(candidates)

    insights = [i for i in insights if not _is_sensitive(i.get("title", "") + i.get("content", ""))]
    return insights, len(candidates)


# ── 策略转换 ──────────────────────────────────────────────────────────────────

_STRATEGY_LABELS = list(STRATEGY_TEMPLATES.keys())


def derive_strategy_from_feedback(
    feedback: str,
    current_label: str | None,
    current_extra: str | None,
) -> tuple[str | None, str | None]:
    """
    用 LLM 分析累积 feedback，返回 (new_label, new_extra)。
    失败时返回 (None, None)，调用方保持原策略不变。
    """
    if not feedback or not feedback.strip():
        return None, None

    labels_str = "、".join(_STRATEGY_LABELS)
    prompt = (
        "你是微信群内容提取策略助手。根据用户对提取结果的历史反馈，推断最合适的群策略配置。\n\n"
        f"## 可选策略标签\n{labels_str}\n\n"
        f"## 当前策略\n标签：{current_label or '（未设置）'}\n补充说明：{current_extra or '（无）'}\n\n"
        f"## 用户历史反馈\n{feedback.strip()}\n\n"
        '## 任务\n分析反馈，输出最合适的策略配置。只输出 JSON，无其他文字：\n'
        '{"label": "策略标签（从可选标签中选一个，或 null 保持不变）", '
        '"extra": "补充说明（简短描述群的特点和提取偏好，或 null 保持不变）"}'
    )

    text = None
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    if text is None:
        try:
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
        except Exception:
            pass

    if text is None:
        return None, None

    m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if not m:
        return None, None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, None

    label = data.get("label") or None
    extra = data.get("extra") or None
    if label and label not in _STRATEGY_LABELS:
        label = None
    return label, extra


# ── 推送 KnowWind ─────────────────────────────────────────────────────────────

def push_insights(
    insights: list[dict],
    group_name: str,
    group_id: str,
    knowwind_url: str,
    knowwind_token: str = "",
) -> int:
    """推送 insights 到 KnowWind，返回成功推送数。"""
    import httpx

    if not insights or not knowwind_url:
        return 0

    url = knowwind_url.rstrip("/") + "/api/insights"
    headers = {"Content-Type": "application/json"}
    if knowwind_token:
        headers["Authorization"] = knowwind_token

    pushed = 0
    for item in insights:
        payload = {
            "source": "wechat",
            "type": item.get("type", "qa"),
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "score": item.get("score", 0),
            "score_reason": item.get("score_reason", ""),
            "occurred_at": item.get("occurred_at", 0),
            "extra": {"group_name": group_name, "group_id": group_id},
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code < 300:
                pushed += 1
        except Exception:
            pass

    return pushed
