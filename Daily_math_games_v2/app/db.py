from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .utils import now_utc_iso


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "daily_math_game.db"
DB_PATH = Path(os.getenv("DAILY_MATH_DB", str(DEFAULT_DB_PATH)))


def _ensure_column(conn: sqlite3.Connection, name: str, ddl: str) -> None:
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(daily_sets)").fetchall()
    }
    if name not in columns:
        conn.execute(f"ALTER TABLE daily_sets ADD COLUMN {name} {ddl}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_sets (
                date TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model_name TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER
            )
            """
        )
        # Handle migrations for older DB files.
        _ensure_column(conn, "model_name", "TEXT")
        _ensure_column(conn, "input_tokens", "INTEGER")
        _ensure_column(conn, "output_tokens", "INTEGER")
        _ensure_column(conn, "total_tokens", "INTEGER")
        conn.commit()


def get_daily_set(date_str: str) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload_json FROM daily_sets WHERE date = ?",
            (date_str,),
        ).fetchone()

    if row is None:
        return None

    return json.loads(row["payload_json"])


def get_daily_meta(date_str: str) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT date, created_at, model_name, input_tokens, output_tokens, total_tokens
            FROM daily_sets
            WHERE date = ?
            """,
            (date_str,),
        ).fetchone()

    if row is None:
        return None

    return {
        "date": row["date"],
        "created_at": row["created_at"],
        "model": row["model_name"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "total_tokens": row["total_tokens"],
    }


def daily_set_exists(date_str: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM daily_sets WHERE date = ? LIMIT 1",
            (date_str,),
        ).fetchone()
    return row is not None


def insert_daily_set(
    date_str: str,
    payload: dict[str, Any],
    *,
    usage: dict[str, int] | None = None,
    model_name: str | None = None,
) -> None:
    payload_json = json.dumps(payload, ensure_ascii=False)
    created_at = now_utc_iso()

    usage = usage or {}
    input_tokens = int(usage.get("input_tokens", 0)) if usage else None
    output_tokens = int(usage.get("output_tokens", 0)) if usage else None
    total_tokens = int(usage.get("total_tokens", 0)) if usage else None

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO daily_sets (
                date,
                payload_json,
                created_at,
                model_name,
                input_tokens,
                output_tokens,
                total_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_str,
                payload_json,
                created_at,
                model_name,
                input_tokens,
                output_tokens,
                total_tokens,
            ),
        )
        conn.commit()
