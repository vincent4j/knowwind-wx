#!/usr/bin/env python3
"""
knowwind-wx CLI

子命令：
  bind    --code CODE --server SERVER  绑定微信账号
  run                                  启动采集守护进程
  status                               查看当前绑定状态
  push-test                            推送测试消息验证流水线
  update                               升级到最新版本
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

# 将项目根目录加入 path（安装前的本地运行支持）
sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import config as cfg
from agent import collector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")


# ── bind ──────────────────────────────────────────────────────────────────────

def cmd_bind(args):
    server = args.server.rstrip("/")
    code = args.code

    # 尝试从 wechat-decrypt 获取真实 wxid；失败则使用 mock
    decrypt_url = os.environ.get("WECHAT_DECRYPT_URL", "http://localhost:5678")
    wxid, nickname = _detect_wechat(decrypt_url)

    print(f"正在绑定... wxid={wxid} nickname={nickname}")

    try:
        resp = httpx.post(
            f"{server}/api/wechat/bind",
            json={"code": code, "wxid": wxid, "nickname": nickname},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ 连接服务器失败: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"❌ 绑定失败 ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    token = data["token"]

    conf = cfg.load() or {}
    conf.update({
        "wxid": wxid,
        "nickname": nickname,
        "token": token,
        "server": server,
        "wechat_decrypt_url": decrypt_url,
        "group_keywords": os.environ.get("GROUP_KEYWORDS", ""),
    })
    cfg.save(conf)

    print(f"✅ 绑定成功")
    print(f"   wxid:     {wxid}")
    print(f"   nickname: {nickname}")
    print(f"   server:   {server}")
    print(f"   配置已保存至 {cfg.CONFIG_PATH}")


def _detect_wechat(decrypt_url: str) -> tuple[str, str]:
    """尝试从 wechat-decrypt 获取当前登录微信的 wxid。失败时返回测试占位值。"""
    try:
        resp = httpx.get(f"{decrypt_url.rstrip('/')}/api/info", timeout=5)
        if resp.status_code == 200:
            info = resp.json()
            wxid = info.get("wxid") or info.get("username") or ""
            nickname = info.get("nickname") or info.get("name") or ""
            if wxid:
                return wxid, nickname
    except Exception:
        pass

    # wechat-decrypt 未运行：使用 mock（供测试用）
    mock_id = f"mock_wxid_{uuid.uuid4().hex[:6]}"
    print("⚠️  wechat-decrypt 未运行，使用 mock wxid（仅供测试）")
    return mock_id, "测试账号"


# ── run ───────────────────────────────────────────────────────────────────────

def cmd_run(args):
    conf = cfg.load()
    if not conf or not conf.get("token"):
        print("❌ 未绑定，请先执行 knowwind-wx bind --code CODE --server SERVER", file=sys.stderr)
        sys.exit(1)

    if args.group_keywords:
        conf["group_keywords"] = args.group_keywords
        cfg.save(conf)

    interval = args.interval
    collector.run_forever(conf, interval=interval)


# ── status ────────────────────────────────────────────────────────────────────

def cmd_status(args):
    conf = cfg.load()
    if not conf:
        print("未绑定（配置文件不存在）")
        return

    server = conf.get("server", "?")
    wxid = conf.get("wxid", "?")
    nickname = conf.get("nickname", "?")
    print(f"绑定状态: ✅ 已绑定")
    print(f"  server:   {server}")
    print(f"  wxid:     {wxid}")
    print(f"  nickname: {nickname}")
    print(f"  配置文件: {cfg.CONFIG_PATH}")

    # 测试连接：用 groups/sync 发一次空心跳（push token 鉴权）
    token = conf.get("token", "")
    if token and not args.no_ping:
        try:
            resp = httpx.post(
                f"{server.rstrip('/')}/api/wechat/groups/sync",
                json={"groups": []},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            if resp.status_code == 200:
                print(f"  服务器侧: ✅ 连接正常（push token 有效）")
            elif resp.status_code == 401:
                print(f"  服务器侧: ❌ push token 无效或已过期")
            else:
                print(f"  服务器侧: ⚠️  {resp.status_code}")
        except Exception as e:
            print(f"  服务器侧: ❌ 连接失败 ({e})")


# ── push-test ─────────────────────────────────────────────────────────────────

def cmd_push_test(args):
    conf = cfg.load()
    if not conf or not conf.get("token"):
        print("❌ 未绑定", file=sys.stderr)
        sys.exit(1)

    server = conf["server"].rstrip("/")
    token = conf["token"]
    group_wxid = args.group_wxid or "test_group_001@chatroom"
    group_name = args.group_name or "测试群"
    content = args.content or f"这是一条测试消息，时间戳 {int(time.time())}"

    payload = {
        "group_wxid": group_wxid,
        "group_name": group_name,
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "timestamp": int(time.time()),
                "type": "text",
                "sender": conf.get("nickname") or "测试用户",
                "content": content,
            }
        ],
    }

    print(f"推送测试消息到 {server}/api/ingest ...")
    print(f"  群: {group_name} ({group_wxid})")
    print(f"  内容: {content}")

    try:
        resp = httpx.post(
            f"{server}/api/ingest",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ 请求失败: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 200:
        result = resp.json()
        print(f"✅ 推送成功: 收到 {result['received']} 条，匹配 {result['routed_sources']} 个信息源")
    else:
        print(f"❌ 推送失败 ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)


# ── update ────────────────────────────────────────────────────────────────────

def cmd_update(args):
    install_dir = str(Path(__file__).parent.parent)

    if not os.path.exists(os.path.join(install_dir, ".git")):
        print("❌ 当前安装不是 git 仓库，无法自动更新。", file=sys.stderr)
        print("   请重新运行安装脚本：curl -fsSL https://raw.githubusercontent.com/vincent4j/knowwind-wx/main/install.sh | sh")
        sys.exit(1)

    print("→ 拉取最新版本...")
    result = subprocess.run(
        ["git", "pull", "--quiet"],
        cwd=install_dir,
    )
    if result.returncode != 0:
        print("❌ 更新失败，请检查网络后重试", file=sys.stderr)
        sys.exit(1)

    subprocess.run(
        ["git", "submodule", "update", "--init", "--quiet"],
        cwd=install_dir,
    )

    print("→ 更新 Python 依赖...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", "httpx", "python-dotenv"])

    print("✅ 更新完成")
    print()
    print("   如果微信客户端有更新，请重新运行：knowwind-wx-decrypt")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="knowwind-wx",
        description="KnowWind 微信采集工具",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # bind
    p_bind = sub.add_parser("bind", help="绑定微信账号到 KnowWind")
    p_bind.add_argument("--code", required=True, help="绑定码（从 KnowWind 平台管理页获取）")
    p_bind.add_argument("--server", required=True, help="KnowWind 服务器地址，如 http://localhost:8000")

    # run
    p_run = sub.add_parser("run", help="启动采集守护进程")
    p_run.add_argument("--interval", type=int, default=60, help="采集间隔（秒，默认 60）")
    p_run.add_argument("--group-keywords", help="群关键词（逗号分隔），覆盖配置文件中的值")

    # status
    p_status = sub.add_parser("status", help="查看绑定状态")
    p_status.add_argument("--no-ping", action="store_true", help="不测试服务器连接")

    # push-test
    p_push = sub.add_parser("push-test", help="推送测试消息验证流水线")
    p_push.add_argument("--group-wxid", help="群 wxid（默认 test_group_001@chatroom）")
    p_push.add_argument("--group-name", help="群名称（默认「测试群」）")
    p_push.add_argument("--content", help="消息内容")

    # update
    sub.add_parser("update", help="升级 knowwind-wx 到最新版本")

    args = parser.parse_args()

    if args.cmd == "bind":
        cmd_bind(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "push-test":
        cmd_push_test(args)
    elif args.cmd == "update":
        cmd_update(args)


if __name__ == "__main__":
    main()
