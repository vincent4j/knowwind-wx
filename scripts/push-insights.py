#!/usr/bin/env python3
"""
push-insights.py — 推送 insights 给 KnowWind REST API

用法：
  echo '[...]' | python3 scripts/push-insights.py --group-id xxx --group-name "AI大航海"
  cat insights.json | python3 scripts/push-insights.py --group-id xxx --group-name "AI大航海"

输入：stdin 或 --input FILE，JSON 数组（insight 格式）
输出：推送结果到 stderr，成功数到 stdout
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.insights import push_insights  # noqa: E402


def _load_config():
    config_path = Path(__file__).parent.parent / "config.sh"
    if not config_path.exists():
        return
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(?:export\s+)?(\w+)="?([^"#${]*)"?$', line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"')
            if key not in os.environ and val:
                os.environ[key] = val


def main():
    _load_config()

    parser = argparse.ArgumentParser(description="推送 insights 给 KnowWind")
    parser.add_argument("--input", "-i", help="insight JSON 文件（默认读 stdin）")
    parser.add_argument("--group-id", required=True, help="群 ID")
    parser.add_argument("--group-name", required=True, help="群名称")
    args = parser.parse_args()

    if args.input:
        insights = json.loads(Path(args.input).read_text(encoding="utf-8"))
    else:
        insights = json.load(sys.stdin)

    knowwind_url = os.environ.get("KNOWWIND_URL", "http://localhost:8000")
    knowwind_token = os.environ.get("KNOWWIND_TOKEN", "")

    pushed = push_insights(insights, args.group_name, args.group_id, knowwind_url, knowwind_token)
    print(f"推送完成：{pushed}/{len(insights)} 条成功", file=sys.stderr)
    print(pushed)


if __name__ == "__main__":
    main()
