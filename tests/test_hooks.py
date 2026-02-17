"""Tests for windsurf_teacher.hooks.capture_session module."""

from __future__ import annotations

import json

import pytest

from windsurf_teacher.db import get_db
from windsurf_teacher.hooks.capture_session import (
    _extract_learn_comments,
    _handle_post_cascade_response,
    _handle_post_run_command,
    _handle_post_write_code,
)


@pytest.fixture
def db_conn(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    yield conn
    conn.close()


class TestExtractLearnComments:
    def test_extracts_single_comment(self):
        text = "x = 5  # LEARN: assignment basics"
        assert _extract_learn_comments(text) == ["assignment basics"]

    def test_extracts_multiple_comments(self):
        text = "# LEARN: first thing\ncode\n# LEARN: second thing"
        result = _extract_learn_comments(text)
        assert result == ["first thing", "second thing"]

    def test_no_comments(self):
        assert _extract_learn_comments("just code") == []

    def test_handles_extra_spaces(self):
        text = "#  LEARN:  spaced out"
        assert _extract_learn_comments(text) == ["spaced out"]


class TestHandlePostCascadeResponse:
    def test_stores_response(self, db_conn):
        data = {
            "agent_action_name": "post_cascade_response",
            "trajectory_id": "traj-1",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {"response": "Here is an explanation."},
        }
        _handle_post_cascade_response(db_conn, data)

        row = db_conn.execute("SELECT * FROM responses").fetchone()
        assert row["response_text"] == "Here is an explanation."
        assert row["response_type"] == "raw"
        assert row["session_id"] == "traj-1"

    def test_extracts_learn_comments_from_response(self, db_conn):
        data = {
            "agent_action_name": "post_cascade_response",
            "trajectory_id": "traj-2",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {"response": "```python\nx = 1  # LEARN: integers are immutable\n```"},
        }
        _handle_post_cascade_response(db_conn, data)

        concepts = db_conn.execute("SELECT * FROM concepts").fetchall()
        assert len(concepts) == 1
        assert "integers are immutable" in concepts[0]["explanation"]
        assert concepts[0]["source"] == "hook"

    def test_skips_empty_response(self, db_conn):
        data = {
            "agent_action_name": "post_cascade_response",
            "trajectory_id": "traj-3",
            "tool_info": {"response": ""},
        }
        _handle_post_cascade_response(db_conn, data)
        assert db_conn.execute("SELECT count(*) FROM responses").fetchone()[0] == 0

    def test_creates_session_on_first_event(self, db_conn):
        data = {
            "agent_action_name": "post_cascade_response",
            "trajectory_id": "new-session",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {"response": "hello"},
        }
        _handle_post_cascade_response(db_conn, data)
        session = db_conn.execute("SELECT * FROM sessions WHERE id = 'new-session'").fetchone()
        assert session is not None


class TestHandlePostWriteCode:
    def test_stores_code_change(self, db_conn):
        data = {
            "agent_action_name": "post_write_code",
            "trajectory_id": "traj-10",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {
                "file_path": "/Users/me/project/src/app.py",
                "edits": [{"old_string": "pass", "new_string": "return 42"}],
            },
        }
        _handle_post_write_code(db_conn, data)

        row = db_conn.execute("SELECT * FROM code_changes").fetchone()
        assert row["file_path"] == "/Users/me/project/src/app.py"
        assert row["old_code"] == "pass"
        assert row["new_code"] == "return 42"

    def test_extracts_learn_from_new_code(self, db_conn):
        data = {
            "agent_action_name": "post_write_code",
            "trajectory_id": "traj-11",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {
                "file_path": "/Users/me/project/file.py",
                "edits": [{"old_string": "", "new_string": "x = {}  # LEARN: dict literal is faster than dict()"}],
            },
        }
        _handle_post_write_code(db_conn, data)

        concepts = db_conn.execute("SELECT * FROM concepts").fetchall()
        assert len(concepts) == 1
        assert "dict literal" in concepts[0]["explanation"]

    def test_skips_empty_file_path(self, db_conn):
        data = {
            "agent_action_name": "post_write_code",
            "trajectory_id": "traj-12",
            "tool_info": {"file_path": "", "edits": []},
        }
        _handle_post_write_code(db_conn, data)
        assert db_conn.execute("SELECT count(*) FROM code_changes").fetchone()[0] == 0

    def test_handles_multiple_edits(self, db_conn):
        data = {
            "agent_action_name": "post_write_code",
            "trajectory_id": "traj-13",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {
                "file_path": "/file.py",
                "edits": [
                    {"old_string": "a", "new_string": "b"},
                    {"old_string": "c", "new_string": "d"},
                ],
            },
        }
        _handle_post_write_code(db_conn, data)
        assert db_conn.execute("SELECT count(*) FROM code_changes").fetchone()[0] == 2


class TestHandlePostRunCommand:
    def test_stores_command(self, db_conn):
        data = {
            "agent_action_name": "post_run_command",
            "trajectory_id": "traj-20",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {"command_line": "pytest -v", "cwd": "/Users/me/project"},
        }
        _handle_post_run_command(db_conn, data)

        row = db_conn.execute("SELECT * FROM commands").fetchone()
        assert row["command_line"] == "pytest -v"
        assert row["working_dir"] == "/Users/me/project"

    def test_skips_empty_command(self, db_conn):
        data = {
            "agent_action_name": "post_run_command",
            "trajectory_id": "traj-21",
            "tool_info": {"command_line": "", "cwd": ""},
        }
        _handle_post_run_command(db_conn, data)
        assert db_conn.execute("SELECT count(*) FROM commands").fetchone()[0] == 0


class TestMainEntryPoint:
    def test_full_dispatch_via_stdin(self, tmp_path, monkeypatch):
        """Integration test: simulate stdin JSON and verify DB write."""
        db_path = tmp_path / "test.db"

        monkeypatch.setattr("windsurf_teacher.hooks.capture_session.get_db", lambda: get_db(db_path))

        payload = json.dumps({
            "agent_action_name": "post_cascade_response",
            "trajectory_id": "integration-1",
            "timestamp": "2025-01-01T00:00:00Z",
            "tool_info": {"response": "Test response"},
        })

        import io

        monkeypatch.setattr("sys.stdin", io.StringIO(payload))

        from windsurf_teacher.hooks.capture_session import main

        main()

        conn = get_db(db_path)
        try:
            row = conn.execute("SELECT * FROM responses").fetchone()
            assert row["response_text"] == "Test response"
        finally:
            conn.close()
