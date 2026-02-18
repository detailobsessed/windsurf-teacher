"""Tests for windsurf_teacher.cli module."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from windsurf_teacher.db import get_db


@pytest.fixture
def _patch_db(tmp_path, monkeypatch):
    """Patch get_db in cli to use a temp database."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("windsurf_teacher.cli.get_db", lambda: get_db(db_path))
    monkeypatch.setattr("windsurf_teacher.mcp_server.get_db", lambda: get_db(db_path))


@pytest.fixture
def db_conn(tmp_path, _patch_db):
    db_path = tmp_path / "test.db"
    conn = get_db(db_path)
    yield conn
    conn.close()


@pytest.mark.usefixtures("_patch_db")
class TestStats:
    def test_stats_empty_db(self, capsys):
        from windsurf_teacher.cli import stats

        stats()
        out = capsys.readouterr().out
        assert "Sessions:  0" in out
        assert "Concepts:  0" in out

    def test_stats_with_data(self, db_conn, capsys):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01', 'test', 'test concept', 'python,testing', 'mcp')"
        )
        db_conn.commit()

        from windsurf_teacher.cli import stats

        stats()
        out = capsys.readouterr().out
        assert "Sessions:  1" in out
        assert "Concepts:  1" in out
        assert "python" in out


@pytest.mark.usefixtures("_patch_db")
class TestSearch:
    def test_search_no_results(self, capsys):
        from windsurf_teacher.cli import search

        search("nonexistent")
        out = capsys.readouterr().out
        assert "No concepts found" in out

    def test_search_finds_concept(self, db_conn, capsys):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01', 'decorator', 'wraps functions', 'python', 'hook')"
        )
        db_conn.commit()

        from windsurf_teacher.cli import search

        search("decorator")
        out = capsys.readouterr().out
        assert "decorator" in out


@pytest.mark.usefixtures("_patch_db")
class TestReview:
    def test_review_no_concepts(self, capsys):
        from windsurf_teacher.cli import review

        review()
        out = capsys.readouterr().out
        assert "up to date" in out

    def test_review_shows_unreviewed(self, db_conn, capsys):
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', '2025-01-01')")
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', '2025-01-01', 'pathlib', 'object paths', '', 'mcp')"
        )
        db_conn.commit()

        from windsurf_teacher.cli import review

        review()
        out = capsys.readouterr().out
        assert "pathlib" in out
        assert "never reviewed" in out


@pytest.mark.usefixtures("_patch_db")
class TestExport:
    def test_export_to_stdout(self, db_conn, capsys):
        now = datetime.now(tz=UTC).isoformat()
        db_conn.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', ?)", (now,))
        db_conn.execute(
            "INSERT INTO concepts (session_id, timestamp, name, explanation, tags, source) "
            "VALUES ('s1', ?, 'test', 'test concept', '', 'mcp')",
            (now,),
        )
        db_conn.commit()

        from windsurf_teacher.cli import export

        export(days=7)
        out = capsys.readouterr().out
        assert "Learning Review" in out

    def test_export_to_file(self, db_conn, tmp_path):
        from windsurf_teacher.cli import export

        output_path = str(tmp_path / "export.md")
        export(days=365, output=output_path)
        assert (tmp_path / "export.md").exists()


class TestMain:
    def test_main_no_args(self):
        from windsurf_teacher.cli import main

        with pytest.raises(SystemExit):
            main()
