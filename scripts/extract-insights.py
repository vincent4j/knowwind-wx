#!/usr/bin/env python3
"""
extract-insights.py — 规则粗过滤 + LLM 精提取

用法：
  echo '[...]' | python3 scripts/extract-insights.py --strategy-label 技术问答群
  cat messages.json | python3 scripts/extract-insights.py --strategy-extra "重点关注 AI 工具"

输入：stdin 或 --input FILE，JSON 数组（wechat-decrypt 消息格式）
输出：stdout，JSON 数组（insight 格式）
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.insights import extract_insights  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="从微信群消息中提取 insights")
    parser.add_argument("--input", "-i", help="消息 JSON 文件（默认读 stdin）")
    parser.add_argument("--strategy-label", default=None, help="策略标签")
    parser.add_argument("--strategy-extra", default=None, help="自定义补充")
    parser.add_argument("--strategy-feedback", default=None, help="历史反馈")
    args = parser.parse_args()

    if args.input:
        messages = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        messages = json.load(sys.stdin)

    insights, candidate_count = extract_insights(
        messages,
        strategy_label=args.strategy_label,
        strategy_extra=args.strategy_extra,
        strategy_feedback=args.strategy_feedback,
    )

    print(json.dumps(insights, ensure_ascii=False, indent=2))
    print(f"候选消息：{candidate_count} 条，提取 insight：{len(insights)} 条", file=sys.stderr)


if __name__ == "__main__":
    main()
