"""Tests for windsurf_teacher.mcp_server module."""

from __future__ import annotations

import pytest

from windsurf_teacher.db import get_db
from windsurf_teacher.mcp_server import (
    export_review_markdown,
    get_learning_gaps,
    get_session_summary,
    log_concept,
    log_gotcha,
    log_pattern,
    query_concepts,
)


@pytest.fixture
def _patch_db(tmp_path, monkeypatch):
    """Patch get_db in mcp_server to use a temp database."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("windsurf_teacher.mcp_server.get_db", lambda: get_db(db_path))


@pytest.fixture
def db_conn(tmp_path, _patch_db):
    """Return a connection to the same patched database."""
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    yield conn
    conn.close()


@pytest.mark.usefixtures("_patch_db")
class TestLogConcept:
    def test_logs_concept(self):
        result = log_concept(name="walrus operator", explanation=":= assigns and returns")
        assert "walrus operator" in result
        assert "logged" in result

    def test_logs_with_tags(self):
        result = log_concept(name="fstring", explanation="formatted strings", tags=["python", "syntax"])
        assert "fstring" in result

    def test_concept_stored_in_db(self, db_conn):
        log_concept(name="generator", explanation="yields values", code_example="yield x", tags=["python"])
        row = db_conn.execute("SELECT * FROM concepts WHERE name = 'generator'").fetchone()
        assert row is not None
        assert row["source"] == "mcp"
        assert row["code_example"] == "yield x"
        assert "python" in row["tags"]


@pytest.mark.usefixtures("_patch_db")
class TestLogPattern:
    def test_logs_new_pattern(self):
        result = log_pattern(name="factory", description="creates objects")
        assert "factory" in result
        assert "logged" in result

    def test_increments_existing_pattern(self):
        log_pattern(name="singleton", description="one instance")
        result = log_pattern(name="singleton", description="one instance only")
        assert "seen 2 times" in result

    def test_pattern_stored_in_db(self, db_conn):
        log_pattern(name="observer", description="event subscription", tags=["design"])
        row = db_conn.execute("SELECT * FROM patterns WHERE name = 'observer'").fetchone()
        assert row is not None
        assert row["times_seen"] == 1
        assert "design" in row["tags"]


@pytest.mark.usefixtures("_patch_db")
class TestLogGotcha:
    def test_logs_gotcha(self):
        result = log_gotcha(description="mutable default args")
        assert "logged" in result
        assert "warning" in result

    def test_logs_with_severity(self):
        result = log_gotcha(description="sql injection", severity="danger")
        assert "danger" in result

    def test_links_to_concept(self, db_conn):
        log_concept(name="dict.get", explanation="returns None by default")
        log_gotcha(description="forgot default", concept_name="dict.get")
        gotcha = db_conn.execute("SELECT * FROM gotchas").fetchone()
        assert gotcha["concept_id"] is not None

    def test_unlinked_gotcha(self, db_conn):
        log_gotcha(description="standalone gotcha", concept_name="nonexistent")
        gotcha = db_conn.execute("SELECT * FROM gotchas").fetchone()
        assert gotcha["concept_id"] is None


@pytest.mark.usefixtures("_patch_db")
class TestQueryConcepts:
    def test_returns_recent_when_no_filters(self):
        log_concept(name="abc", explanation="abstract base class")
        result = query_concepts()
        assert "abc" in result

    def test_search_by_text(self):
        log_concept(name="decorator", explanation="wraps functions")
        result = query_concepts(search="decorator")
        assert "decorator" in result

    def test_search_by_tags(self):
        log_concept(name="asyncio", explanation="async framework", tags=["concurrency"])
        result = query_concepts(tags="concurrency")
        assert "asyncio" in result

    def test_no_results(self):
        result = query_concepts(search="zzzznonexistent")
        assert "No concepts found" in result

    def test_limit(self):
        for i in range(5):
            log_concept(name=f"concept-{i}", explanation=f"explanation {i}")
        result = query_concepts(limit=2)
        assert result.count("- **") == 2


@pytest.mark.usefixtures("_patch_db")
class TestGetLearningGaps:
    def test_returns_unreviewed_concepts(self):
        log_concept(name="pathlib", explanation="object-oriented paths")
        result = get_learning_gaps()
        assert "pathlib" in result
        assert "never reviewed" in result

    def test_no_gaps(self):
        result = get_learning_gaps()
        assert "up to date" in result


@pytest.mark.usefixtures("_patch_db")
class TestExportReviewMarkdown:
    def test_export_with_concepts(self):
        log_concept(name="context manager", explanation="with statement", tags=["python"])
        log_pattern(name="factory", description="object creation")
        log_gotcha(description="mutable defaults")
        result = export_review_markdown(days=1)
        assert "# Learning Review" in result
        assert "context manager" in result
        assert "factory" in result
        assert "mutable defaults" in result

    def test_export_empty(self):
        result = export_review_markdown(days=0)
        assert "No learnings found" in result


@pytest.mark.usefixtures("_patch_db")
class TestGetSessionSummary:
    def test_no_sessions(self):
        result = get_session_summary()
        assert "No sessions found" in result

    def test_summary_of_session(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at, project_path) VALUES ('s1', '2025-01-01T00:00:00', '/project')")
        db_conn.execute("INSERT INTO responses (session_id, timestamp, response_text) VALUES ('s1', '2025-01-01T00:00:00', 'hi')")
        db_conn.commit()
        result = get_session_summary(session_id="s1")
        assert "s1" in result
        assert "1 responses" in result

    def test_most_recent_session(self, db_conn):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('old', '2024-01-01T00:00:00')")
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('new', '2025-06-01T00:00:00')")
        db_conn.commit()
        result = get_session_summary()
        assert "new" in result
