import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "wx_still.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                strategy_label TEXT,
                strategy_extra TEXT,
                strategy_feedback TEXT,
                last_fetched_at INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fetch_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                message_count INTEGER,
                candidate_count INTEGER,
                insight_count INTEGER,
                pushed_count INTEGER,
                status TEXT,
                error TEXT
            );
        """)


# ── groups ────────────────────────────────────────────────────────────────────

def list_groups() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def get_group(group_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
        return dict(row) if row else None


def upsert_group(group_id: str, name: str, enabled: bool = True) -> dict:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO groups (id, name, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at
        """, (group_id, name, 1 if enabled else 0, now, now))
    return get_group(group_id)


def update_strategy(group_id: str, label: str | None, extra: str | None) -> dict | None:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute("""
            UPDATE groups SET strategy_label=?, strategy_extra=?, updated_at=?
            WHERE id=?
        """, (label, extra, now, group_id))
    return get_group(group_id)


def update_enabled(group_id: str, enabled: bool) -> dict | None:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            "UPDATE groups SET enabled=?, updated_at=? WHERE id=?",
            (1 if enabled else 0, now, group_id)
        )
    return get_group(group_id)


def append_feedback(group_id: str, feedback_line: str):
    now = int(time.time())
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strategy_feedback FROM groups WHERE id=?", (group_id,)
        ).fetchone()
        if row is None:
            return
        existing = (row["strategy_feedback"] or "").strip()
        updated = (existing + "\n" + feedback_line).strip()
        conn.execute(
            "UPDATE groups SET strategy_feedback=?, updated_at=? WHERE id=?",
            (updated, now, group_id)
        )


def update_last_fetched(group_id: str, ts: int):
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            "UPDATE groups SET last_fetched_at=?, updated_at=? WHERE id=?",
            (ts, now, group_id)
        )


# ── fetch_logs ────────────────────────────────────────────────────────────────

def insert_log(
    group_id: str,
    message_count: int | None = None,
    candidate_count: int | None = None,
    insight_count: int | None = None,
    pushed_count: int | None = None,
    status: str = "success",
    error: str | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO fetch_logs
                (group_id, fetched_at, message_count, candidate_count,
                 insight_count, pushed_count, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (group_id, int(time.time()), message_count, candidate_count,
              insight_count, pushed_count, status, error))
        return cur.lastrowid


def list_logs(group_id: str | None = None, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        if group_id:
            rows = conn.execute(
                "SELECT * FROM fetch_logs WHERE group_id=? ORDER BY fetched_at DESC LIMIT ?",
                (group_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM fetch_logs ORDER BY fetched_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
