"""Tests for windsurf_teacher.db module."""

from __future__ import annotations

import sqlite3

import pytest

from windsurf_teacher.db import _SCHEMA_VERSION, get_db


@pytest.fixture
def db_conn(tmp_path):
    """Return a fresh in-memory-like db connection using a temp file."""
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    yield conn
    conn.close()


class TestGetDb:
    def test_creates_database_file(self, tmp_path):
        db_path = tmp_path / "sub" / "test.db"
        conn = get_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_returns_connection_with_row_factory(self, db_conn):
        assert db_conn.row_factory is sqlite3.Row

    def test_wal_mode_enabled(self, db_conn):
        mode = db_conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db_conn):
        fk = db_conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_schema_version_set(self, db_conn):
        row = db_conn.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == _SCHEMA_VERSION

    def test_idempotent_init(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn1 = get_db(db_path)
        conn1.close()
        conn2 = get_db(db_path)
        row = conn2.execute("SELECT version FROM schema_version").fetchone()
        assert row["version"] == _SCHEMA_VERSION
        conn2.close()


class TestTables:
    def test_sessions_table_exists(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        row = db_conn.execute("SELECT id FROM sessions WHERE id = 's1'").fetchone()
        assert row["id"] == "s1"

    def test_responses_table_defaults(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        db_conn.execute("INSERT INTO responses (session_id, timestamp, response_text) VALUES ('s1', '2025-01-01T00:00:00', 'hello')")
        row = db_conn.execute("SELECT response_type FROM responses").fetchone()
        assert row["response_type"] == "raw"

    def test_concepts_table_insert(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01T00:00:00', 'walrus', 'assignment expression', 'python,syntax', 'hook')"
        )
        row = db_conn.execute("SELECT * FROM concepts WHERE name = 'walrus'").fetchone()
        assert row["explanation"] == "assignment expression"
        assert row["review_count"] == 0

    def test_patterns_table_unique_name(self, db_conn):
        db_conn.execute("INSERT INTO patterns (name, description, first_seen) VALUES ('factory', 'creates objects', '2025-01-01')")
        with pytest.raises(sqlite3.IntegrityError):
            db_conn.execute("INSERT INTO patterns (name, description, first_seen) VALUES ('factory', 'dup', '2025-01-02')")

    def test_gotchas_table_nullable_concept(self, db_conn):
        db_conn.execute("INSERT INTO gotchas (description, severity) VALUES ('watch out', 'warning')")
        row = db_conn.execute("SELECT * FROM gotchas").fetchone()
        assert row["concept_id"] is None
        assert row["severity"] == "warning"


class TestFTS:
    def test_fts_search_by_name(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01T00:00:00', 'context manager', 'with statement protocol', 'python', 'mcp')"
        )
        rows = db_conn.execute(
            "SELECT * FROM concepts_fts WHERE concepts_fts MATCH 'context'",
        ).fetchall()
        assert len(rows) == 1
        assert "context manager" in rows[0]["name"]

    def test_fts_search_by_tags(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01T00:00:00', 'decorator', 'wraps functions', 'python,patterns', 'hook')"
        )
        rows = db_conn.execute(
            "SELECT * FROM concepts_fts WHERE concepts_fts MATCH 'patterns'",
        ).fetchall()
        assert len(rows) == 1

    def test_fts_updates_on_concept_update(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01T00:00:00', 'generator', 'yields values', 'python', 'hook')"
        )
        db_conn.execute("UPDATE concepts SET explanation = 'lazy iteration' WHERE name = 'generator'")
        rows = db_conn.execute(
            "SELECT * FROM concepts_fts WHERE concepts_fts MATCH 'lazy'",
        ).fetchall()
        assert len(rows) == 1

    def test_fts_updates_on_concept_delete(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01T00:00:00')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01T00:00:00', 'comprehension', 'list building', 'python', 'hook')"
        )
        db_conn.execute("DELETE FROM concepts WHERE name = 'comprehension'")
        rows = db_conn.execute(
            "SELECT * FROM concepts_fts WHERE concepts_fts MATCH 'comprehension'",
        ).fetchall()
        assert len(rows) == 0
