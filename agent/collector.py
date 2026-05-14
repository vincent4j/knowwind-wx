"""
collector.py — 从 wechat-decrypt 拉取消息，推送到 KnowWind /api/ingest
              同时定期同步群列表（作为心跳）
"""

import hashlib
import logging
import time
import uuid
from typing import Generator

import httpx

logger = logging.getLogger("agent.collector")

# wechat-decrypt 消息字段映射
# 格式: { id, timestamp, type, sender, chat, username, is_group, content }


def _fetch_messages(decrypt_url: str, since: int = 0, limit: int = 2000) -> list[dict]:
    resp = httpx.get(
        f"{decrypt_url.rstrip('/')}/api/history",
        params={"since": since, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _group_messages(
    messages: list[dict], keywords: list[str]
) -> dict[str, dict]:
    """按群 wxid 分组，返回 { group_wxid: {name, messages: [...]} }"""
    groups: dict[str, dict] = {}
    for m in messages:
        if not m.get("is_group"):
            continue
        chat = (m.get("chat") or "").strip()
        group_wxid = (m.get("username") or "").strip()
        if not chat or not group_wxid:
            continue
        if keywords and not any(kw in chat for kw in keywords):
            continue
        if group_wxid not in groups:
            groups[group_wxid] = {"name": chat, "messages": []}
        groups[group_wxid]["messages"].append(m)
    return groups


def _to_ingest_msg(m: dict) -> dict:
    return {
        "id": m.get("id") or hashlib.md5(
            f"{m.get('username')}{m.get('timestamp')}{m.get('content','')}".encode()
        ).hexdigest(),
        "timestamp": int(m.get("timestamp") or time.time()),
        "type": m.get("type") or "text",
        "sender": m.get("sender") or m.get("from") or None,
        "content": (m.get("content") or "").strip(),
    }


def sync_groups(config: dict) -> int:
    """向 KnowWind 同步群列表，同时更新 last_seen_at（心跳）。"""
    server = config["server"].rstrip("/")
    token = config["token"]
    keywords = [k.strip() for k in config.get("group_keywords", "").split(",") if k.strip()]
    decrypt_url = config.get("wechat_decrypt_url", "http://localhost:5678")

    try:
        messages = _fetch_messages(decrypt_url)
    except Exception as e:
        logger.warning("wechat-decrypt 拉取失败: %s", e)
        return 0

    groups = _group_messages(messages, keywords)
    if not groups:
        logger.debug("未发现匹配群")
        return 0

    group_list = [
        {"group_wxid": gid, "group_name": info["name"], "member_count": None}
        for gid, info in groups.items()
    ]

    resp = httpx.post(
        f"{server}/api/wechat/groups/sync",
        json={"groups": group_list},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    synced = resp.json().get("synced", 0)
    logger.info("群同步完成: %d 个群", synced)
    return synced


def collect_and_push(config: dict, since: int = 0) -> tuple[int, int]:
    """
    拉取自 `since` 起的新消息，按群推送到 /api/ingest。
    返回 (total_messages, total_groups_pushed)
    """
    server = config["server"].rstrip("/")
    token = config["token"]
    keywords = [k.strip() for k in config.get("group_keywords", "").split(",") if k.strip()]
    decrypt_url = config.get("wechat_decrypt_url", "http://localhost:5678")

    try:
        messages = _fetch_messages(decrypt_url, since=since)
    except Exception as e:
        logger.warning("wechat-decrypt 拉取失败: %s", e)
        return 0, 0

    groups = _group_messages(messages, keywords)
    if not groups:
        return 0, 0

    total_msgs = 0
    pushed_groups = 0
    for group_wxid, info in groups.items():
        msgs = [_to_ingest_msg(m) for m in info["messages"] if m.get("content")]
        if not msgs:
            continue
        try:
            resp = httpx.post(
                f"{server}/api/ingest",
                json={
                    "group_wxid": group_wxid,
                    "group_name": info["name"],
                    "messages": msgs,
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(
                "ingest: 群=%s 消息=%d 匹配源=%d",
                info["name"], len(msgs), result.get("routed_sources", 0)
            )
            total_msgs += len(msgs)
            pushed_groups += 1
        except Exception as e:
            logger.warning("ingest 推送失败 群=%s: %s", info["name"], e)

    return total_msgs, pushed_groups


def run_forever(config: dict, interval: int = 60) -> None:
    """主循环：每隔 interval 秒拉取并推送新消息 + 同步群（心跳）。"""
    logger.info("knowwind-wx 采集服务启动 (间隔 %ds)", interval)
    last_fetch_at = int(time.time()) - interval  # 首次立即采集

    while True:
        now = int(time.time())
        try:
            sync_groups(config)
            msgs, groups = collect_and_push(config, since=last_fetch_at)
            if msgs > 0:
                logger.info("本轮采集: %d 条消息 / %d 个群", msgs, groups)
            last_fetch_at = now
        except Exception as e:
            logger.error("采集轮次异常: %s", e)

        time.sleep(interval)
