"""SQLite 数据访问层。

表结构（设计文档第 13.1 节 models 目录：user / scenario / provider_config）：
  users            账号
  scenarios        用户保存的算法参数案例（登录后跨设备同步）
  provider_configs 模型厂商接入配置（api_key 字段密文存储）
  usage_logs       游客额度计数（按日期 + 客户端标识）
  model_records    内置小模型下载/加载状态索引

连接策略：SQLite 单文件 + WAL，短连接（每次请求开一个新连接）。
教学场景并发极低，短连接足够且避免线程间共享连接的坑。
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings
from .crypto import harden_file_permissions

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    name        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_scenarios_user ON scenarios(user_id, kind);

CREATE TABLE IF NOT EXISTS provider_configs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER,
    provider_key   TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    base_url       TEXT NOT NULL,
    model          TEXT NOT NULL,
    api_key_cipher TEXT NOT NULL DEFAULT '',
    extra_headers  TEXT NOT NULL DEFAULT '{}',
    is_local       INTEGER NOT NULL DEFAULT 0,
    is_active      INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_user ON provider_configs(user_id, provider_key);

CREATE TABLE IF NOT EXISTS usage_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,
    client_key  TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT NOT NULL,
    UNIQUE (day, client_key)
);

CREATE TABLE IF NOT EXISTS model_records (
    model_id      TEXT PRIMARY KEY,
    state         TEXT NOT NULL,
    file_path     TEXT NOT NULL DEFAULT '',
    bytes_done    INTEGER NOT NULL DEFAULT 0,
    bytes_total   INTEGER NOT NULL DEFAULT 0,
    sha256        TEXT NOT NULL DEFAULT '',
    error         TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL
);
"""

_init_lock = threading.Lock()
_initialized = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with get_conn() as conn:
            conn.executescript(_SCHEMA)
        harden_file_permissions(settings.db_path)
        _initialized = True


def reset_for_tests(db_path: Path) -> None:
    """测试辅助：指向临时库并强制重新初始化。"""
    global _initialized
    object.__setattr__(settings, "data_dir", db_path.parent)
    _initialized = False
    init_db()


# ---------------- users ----------------


def create_user(username: str, password_hash: str, display_name: str | None = None) -> dict[str, Any]:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, display_name or username, _utc_now()),
        )
        return {"id": int(cursor.lastrowid), "username": username, "displayName": display_name or username}


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ---------------- scenarios ----------------


def list_scenarios(user_id: int, kind: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if kind:
            rows = conn.execute(
                "SELECT * FROM scenarios WHERE user_id = ? AND kind = ? ORDER BY updated_at DESC",
                (user_id, kind),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scenarios WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]


def save_scenario(user_id: int, kind: str, name: str, payload: str) -> dict[str, Any]:
    now = _utc_now()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM scenarios WHERE user_id = ? AND kind = ? AND name = ?", (user_id, kind, name)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE scenarios SET payload = ?, updated_at = ? WHERE id = ?", (payload, now, existing["id"])
            )
            return {"id": int(existing["id"]), "name": name, "kind": kind, "updatedAt": now}
        cursor = conn.execute(
            "INSERT INTO scenarios (user_id, kind, name, payload, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, kind, name, payload, now, now),
        )
        return {"id": int(cursor.lastrowid), "name": name, "kind": kind, "updatedAt": now}


def delete_scenario(user_id: int, scenario_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM scenarios WHERE id = ? AND user_id = ?", (scenario_id, user_id))
        return cursor.rowcount > 0


# ---------------- provider_configs ----------------


def list_provider_configs(user_id: int | None) -> list[sqlite3.Row]:
    """返回原始行（含密文列）；对外的掩码投影由 API 层统一负责。"""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM provider_configs WHERE user_id IS ? ORDER BY provider_key", (user_id,)
        ).fetchall()


def get_provider_config(config_id: int, user_id: int | None) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM provider_configs WHERE id = ? AND user_id IS ?", (config_id, user_id)
        ).fetchone()


def get_provider_config_by_key(provider_key: str, user_id: int | None) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM provider_configs WHERE provider_key = ? AND user_id IS ?", (provider_key, user_id)
        ).fetchone()


def upsert_provider_config(
    *,
    user_id: int | None,
    provider_key: str,
    display_name: str,
    base_url: str,
    model: str,
    api_key_cipher: str,
    extra_headers: str,
    is_local: bool,
) -> sqlite3.Row:
    now = _utc_now()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM provider_configs WHERE provider_key = ? AND user_id IS ?", (provider_key, user_id)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE provider_configs SET display_name = ?, base_url = ?, model = ?, api_key_cipher = ?,
                   extra_headers = ?, is_local = ?, updated_at = ? WHERE id = ?""",
                (display_name, base_url, model, api_key_cipher, extra_headers, int(is_local), now, existing["id"]),
            )
            config_id = int(existing["id"])
        else:
            cursor = conn.execute(
                """INSERT INTO provider_configs
                   (user_id, provider_key, display_name, base_url, model, api_key_cipher, extra_headers,
                    is_local, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    user_id,
                    provider_key,
                    display_name,
                    base_url,
                    model,
                    api_key_cipher,
                    extra_headers,
                    int(is_local),
                    now,
                    now,
                ),
            )
            config_id = int(cursor.lastrowid)
        row = conn.execute("SELECT * FROM provider_configs WHERE id = ?", (config_id,)).fetchone()
        return row


def delete_provider_config(config_id: int, user_id: int | None) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM provider_configs WHERE id = ? AND user_id IS ?", (config_id, user_id)
        )
        return cursor.rowcount > 0


def set_active_provider(config_id: int, user_id: int | None) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE provider_configs SET is_active = 0 WHERE user_id IS ?", (user_id,))
        conn.execute("UPDATE provider_configs SET is_active = 1 WHERE id = ?", (config_id,))


def get_active_provider(user_id: int | None) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM provider_configs WHERE user_id IS ? AND is_active = 1 LIMIT 1", (user_id,)
        ).fetchone()


# ---------------- usage_logs ----------------


def increment_usage(client_key: str, day: str | None = None) -> int:
    day = day or date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO usage_logs (day, client_key, count, updated_at) VALUES (?, ?, 1, ?)
               ON CONFLICT(day, client_key) DO UPDATE SET count = count + 1, updated_at = excluded.updated_at""",
            (day, client_key, _utc_now()),
        )
        row = conn.execute(
            "SELECT count FROM usage_logs WHERE day = ? AND client_key = ?", (day, client_key)
        ).fetchone()
        return int(row["count"]) if row else 0


def get_usage(client_key: str, day: str | None = None) -> int:
    day = day or date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM usage_logs WHERE day = ? AND client_key = ?", (day, client_key)
        ).fetchone()
        return int(row["count"]) if row else 0


# ---------------- model_records ----------------


def upsert_model_record(
    model_id: str,
    *,
    state: str,
    file_path: str = "",
    bytes_done: int = 0,
    bytes_total: int = 0,
    sha256: str = "",
    error: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO model_records (model_id, state, file_path, bytes_done, bytes_total, sha256, error, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(model_id) DO UPDATE SET
                 state = excluded.state, file_path = excluded.file_path, bytes_done = excluded.bytes_done,
                 bytes_total = excluded.bytes_total, sha256 = excluded.sha256, error = excluded.error,
                 updated_at = excluded.updated_at""",
            (model_id, state, file_path, bytes_done, bytes_total, sha256, error, _utc_now()),
        )


def get_model_record(model_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM model_records WHERE model_id = ?", (model_id,)).fetchone()


def list_model_records() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM model_records").fetchall()
