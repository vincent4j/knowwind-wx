"""
wx-still 后台服务 — FastAPI，监听 localhost:8001

启动：uvicorn server.main:app --host 127.0.0.1 --port 8001
"""

import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import db
from server import insights as insights_mod

ROOT = Path(__file__).parent.parent

load_dotenv(ROOT / ".env")

WECHAT_DECRYPT_URL = os.environ.get("WECHAT_DECRYPT_URL", "http://localhost:5678").rstrip("/")
GROUP_KEYWORDS = [k.strip() for k in os.environ.get("GROUP_KEYWORDS", "").split(",") if k.strip()]
KNOWWIND_URL = os.environ.get("KNOWWIND_URL", "http://localhost:8000").rstrip("/")
KNOWWIND_TOKEN = os.environ.get("KNOWWIND_TOKEN", "")


def _matches_keywords(chat_name: str) -> bool:
    if not GROUP_KEYWORDS:
        return True
    return any(kw in chat_name for kw in GROUP_KEYWORDS)


# ── 采集状态（内存，重启清零）────────────────────────────────────────────────
_collect_lock = threading.Lock()
_collect_status: dict = {"running": False, "started_at": None, "finished_at": None, "error": None}


# ── 启动/关闭钩子 ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _register_knowwind()
    yield


def _register_knowwind():
    url = os.environ.get("KNOWWIND_URL", "").rstrip("/")
    if not url:
        return
    try:
        httpx.post(
            f"{url}/api/plugins/register",
            json={
                "name": "wechat",
                "display_name": "微信",
                "version": "1.0.0",
                "url": "http://localhost:8001",
                "ui_path": "/ui/index.html",
            },
            timeout=5,
        )
    except Exception:
        pass


# ── FastAPI 应用 ───────────────────────────────────────────────────────────────

app = FastAPI(title="wx-still", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_DIR = ROOT / "ui"
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")


# ── 群同步（从 wechat-decrypt API）──────────────────────────────────────────

def _sync_groups_from_api() -> int:
    """从 wechat-decrypt 拉取历史消息，提取匹配 GROUP_KEYWORDS 的群并 upsert。"""
    try:
        resp = httpx.get(
            f"{WECHAT_DECRYPT_URL}/api/history",
            params={"limit": 2000},
            timeout=10,
        )
        resp.raise_for_status()
        messages = resp.json()
    except Exception as e:
        raise RuntimeError(f"wechat-decrypt 连接失败：{e}")

    seen: dict[str, str] = {}  # username → chat name
    for m in messages:
        if not m.get("is_group"):
            continue
        chat = m.get("chat", "").strip()
        username = m.get("username", "").strip()
        if chat and username and _matches_keywords(chat):
            seen[username] = chat

    for uid, name in seen.items():
        db.upsert_group(uid, name)
    return len(seen)


# ── 采集流程 ─────────────────────────────────────────────────────────────────

def _run_collect():
    error = None
    groups = [g for g in db.list_groups() if g["enabled"]]
    try:
        for g in groups:
            since = g.get("last_fetched_at", 0)
            resp = httpx.get(
                f"{WECHAT_DECRYPT_URL}/api/history",
                params={"chat": g["name"], "since": since, "limit": 2000},
                timeout=30,
            )
            resp.raise_for_status()
            messages = resp.json()

            extracted, candidate_count = insights_mod.extract_insights(
                messages,
                strategy_label=g.get("strategy_label"),
                strategy_extra=g.get("strategy_extra"),
                strategy_feedback=g.get("strategy_feedback"),
            )
            pushed_count = insights_mod.push_insights(
                extracted, g["name"], g["id"], KNOWWIND_URL, KNOWWIND_TOKEN
            )

            db.update_last_fetched(g["id"], int(time.time()))
            db.insert_log(
                group_id=g["id"],
                message_count=len(messages),
                candidate_count=candidate_count,
                insight_count=len(extracted),
                pushed_count=pushed_count,
                status="success",
            )
    except Exception as e:
        error = str(e)
        for g in groups:
            db.insert_log(group_id=g["id"], status="failed", error=error)

    with _collect_lock:
        _collect_status.update(running=False, finished_at=time.time(), error=error)


# ── 路由 ──────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/info")
def info():
    return {
        "name": "wechat",
        "display_name": "微信",
        "version": "1.0.0",
        "url": "http://localhost:8001",
        "ui_path": "/ui/index.html",
    }


@app.get("/groups")
def get_groups():
    return db.list_groups()


class StrategyBody(BaseModel):
    label: str | None = None
    extra: str | None = None
    enabled: bool | None = None


@app.post("/groups/{group_id}/strategy")
def update_group_strategy(group_id: str, body: StrategyBody):
    group = db.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="群不存在")
    if body.enabled is not None:
        db.update_enabled(group_id, body.enabled)
    if body.label is not None or body.extra is not None:
        db.update_strategy(group_id, body.label, body.extra)
    return db.get_group(group_id)


@app.post("/groups/sync")
def sync_groups():
    try:
        synced = _sync_groups_from_api()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"synced": synced}


class CollectBody(BaseModel):
    date: str | None = None


@app.post("/collect")
def trigger_collect(body: CollectBody = CollectBody()):
    with _collect_lock:
        if _collect_status["running"]:
            raise HTTPException(status_code=409, detail="采集正在进行中")
        _collect_status.update(running=True, started_at=time.time(), finished_at=None, error=None)

    thread = threading.Thread(target=_run_collect, daemon=True)
    thread.start()
    return {"message": "采集已启动"}


@app.get("/collect/status")
def collect_status():
    with _collect_lock:
        return dict(_collect_status)


class FeedbackBody(BaseModel):
    group_id: str
    insight_id: str | None = None
    feedback: str


@app.post("/feedback")
def receive_feedback(body: FeedbackBody):
    group = db.get_group(body.group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="群不存在")
    line = f"[{datetime.now().strftime('%Y-%m-%d')}] {body.feedback}"
    db.append_feedback(body.group_id, line)

    updated_group = db.get_group(body.group_id)
    new_label, new_extra = insights_mod.derive_strategy_from_feedback(
        updated_group.get("strategy_feedback") or "",
        updated_group.get("strategy_label"),
        updated_group.get("strategy_extra"),
    )
    if new_label is not None or new_extra is not None:
        db.update_strategy(
            body.group_id,
            new_label if new_label is not None else updated_group.get("strategy_label"),
            new_extra if new_extra is not None else updated_group.get("strategy_extra"),
        )

    return {"message": "反馈已记录", "group": db.get_group(body.group_id)}


@app.get("/logs")
def get_logs(group_id: str | None = None, limit: int = 20):
    return db.list_logs(group_id=group_id, limit=limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=8001, reload=False)
