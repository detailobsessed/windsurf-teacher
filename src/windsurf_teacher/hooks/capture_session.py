#!/usr/bin/env python3
"""Hook capture script for Windsurf Teacher.

Receives JSON via stdin from Windsurf hooks, dispatches by event type,
and writes structured data to the learning SQLite database.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import PurePath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable

from windsurf_teacher.db import get_db

_LEARN_PATTERN = re.compile(r"#\s*LEARN:\s*(.+)")


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _ensure_session(conn, session_id: str, project_path: str | None = None) -> None:
    """Insert session row if it doesn't already exist (race-safe)."""
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, started_at, project_path) VALUES (?, ?, ?)",
        (session_id, _now_iso(), project_path),
    )
    conn.commit()


def _extract_learn_comments(text: str) -> list[str]:
    """Extract all ``# LEARN: ...`` comments from text."""
    return _LEARN_PATTERN.findall(text)


def _handle_post_cascade_response(conn, data: dict) -> None:
    tool_info = data.get("tool_info", {})
    response_text = tool_info.get("response", "")
    if not response_text:
        return

    session_id = data.get("trajectory_id") or f"session-{_now_iso()}"
    _ensure_session(conn, session_id)

    conn.execute(
        "INSERT INTO responses (session_id, timestamp, response_text, response_type) VALUES (?, ?, ?, ?)",
        (session_id, data.get("timestamp", _now_iso()), response_text, "raw"),
    )

    for learn_text in _extract_learn_comments(response_text):
        conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, _now_iso(), learn_text[:80], learn_text, "", "hook"),
        )

    conn.commit()


def _handle_post_write_code(conn, data: dict) -> None:
    tool_info = data.get("tool_info", {})
    file_path = tool_info.get("file_path", "")
    edits = tool_info.get("edits", [])
    if not file_path:
        return

    session_id = data.get("trajectory_id") or f"session-{_now_iso()}"
    fp = PurePath(file_path)
    try:
        src_idx = fp.parts.index("src")
        project_path = str(PurePath(*fp.parts[:src_idx]))
    except ValueError:
        project_path = None
    _ensure_session(conn, session_id, project_path)

    for edit in edits:
        old_code = edit.get("old_string", "")
        new_code = edit.get("new_string", "")
        conn.execute(
            "INSERT INTO code_changes (session_id, timestamp, file_path, old_code, new_code) VALUES (?, ?, ?, ?, ?)",
            (session_id, data.get("timestamp", _now_iso()), file_path, old_code, new_code),
        )

        for learn_text in _extract_learn_comments(new_code):
            conn.execute(
                "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, _now_iso(), learn_text[:80], learn_text, "", "hook"),
            )

    conn.commit()


def _handle_post_run_command(conn, data: dict) -> None:
    tool_info = data.get("tool_info", {})
    command_line = tool_info.get("command_line", "")
    if not command_line:
        return

    session_id = data.get("trajectory_id") or f"session-{_now_iso()}"
    working_dir = tool_info.get("cwd", "")
    _ensure_session(conn, session_id, working_dir or None)

    conn.execute(
        "INSERT INTO commands (session_id, timestamp, command_line, working_dir) VALUES (?, ?, ?, ?)",
        (session_id, data.get("timestamp", _now_iso()), command_line, working_dir),
    )
    conn.commit()


_HANDLERS: dict[str, Callable[[sqlite3.Connection, dict], None]] = {
    "post_cascade_response": _handle_post_cascade_response,
    "post_write_code": _handle_post_write_code,
    "post_run_command": _handle_post_run_command,
}


def main() -> None:
    """Entry point: read JSON from stdin, dispatch to handler, exit 0 always."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        action = data.get("agent_action_name", "")
        handler = _HANDLERS.get(action)
        if handler is None:
            return

        conn = get_db()
        try:
            handler(conn, data)
        finally:
            conn.close()
    except Exception:
        logging.getLogger(__name__).debug("hook capture failed", exc_info=True)


if __name__ == "__main__":
    main()
