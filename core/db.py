"""
db.py
-----
SQLite-Wrapper für das abp Toolboard.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(r"C:\Users\abau\AI Projects\Frontend\data\config.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tools (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    path TEXT NOT NULL,
    type TEXT NOT NULL,
    visible INTEGER NOT NULL DEFAULT 0,
    port INTEGER,
    start_cmd TEXT,
    description TEXT,
    detected_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cli_arg_specs (
    tool_id TEXT NOT NULL,
    arg_name TEXT NOT NULL,
    arg_label TEXT NOT NULL,
    arg_type TEXT NOT NULL,
    default_value TEXT,
    PRIMARY KEY (tool_id, arg_name)
);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.executescript(SCHEMA)


def upsert_tool(tool_dict: dict) -> None:
    """Fügt Tool ein oder aktualisiert nur last_seen_at + path (Nutzereinstellungen bleiben erhalten)."""
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM tools WHERE id = ?", (tool_dict["id"],)
        ).fetchone()
        if existing:
            # Nur path und last_seen_at aktualisieren
            con.execute(
                "UPDATE tools SET path = ?, last_seen_at = ? WHERE id = ?",
                (tool_dict["path"], now, tool_dict["id"]),
            )
        else:
            con.execute(
                """INSERT INTO tools
                   (id, display_name, path, type, visible, port, start_cmd, description, detected_at, last_seen_at)
                   VALUES (?, ?, ?, ?, 0, ?, NULL, NULL, ?, ?)""",
                (
                    tool_dict["id"],
                    tool_dict["display_name"],
                    tool_dict["path"],
                    tool_dict["type"],
                    tool_dict.get("port"),
                    tool_dict.get("detected_at", now),
                    now,
                ),
            )


def get_all_tools(visible_only: bool = False) -> list[dict]:
    with _conn() as con:
        if visible_only:
            rows = con.execute(
                "SELECT * FROM tools WHERE visible = 1 ORDER BY display_name"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM tools ORDER BY display_name"
            ).fetchall()
    return [dict(row) for row in rows]


def get_tool(tool_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM tools WHERE id = ?", (tool_id,)
        ).fetchone()
    return dict(row) if row else None


def update_tool_settings(
    tool_id: str,
    display_name: str,
    visible: int,
    port: int | None,
    description: str | None,
) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE tools
               SET display_name = ?, visible = ?, port = ?, description = ?
               WHERE id = ?""",
            (display_name, visible, port, description, tool_id),
        )


def get_cli_specs(tool_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM cli_arg_specs WHERE tool_id = ? ORDER BY arg_name",
            (tool_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def upsert_cli_spec(
    tool_id: str,
    arg_name: str,
    arg_label: str,
    arg_type: str,
    default_value: str = "",
) -> None:
    with _conn() as con:
        existing = con.execute(
            "SELECT tool_id FROM cli_arg_specs WHERE tool_id = ? AND arg_name = ?",
            (tool_id, arg_name),
        ).fetchone()
        if existing:
            con.execute(
                """UPDATE cli_arg_specs
                   SET arg_label = ?, arg_type = ?, default_value = ?
                   WHERE tool_id = ? AND arg_name = ?""",
                (arg_label, arg_type, default_value, tool_id, arg_name),
            )
        else:
            con.execute(
                """INSERT INTO cli_arg_specs (tool_id, arg_name, arg_label, arg_type, default_value)
                   VALUES (?, ?, ?, ?, ?)""",
                (tool_id, arg_name, arg_label, arg_type, default_value),
            )
