"""SQLite database schema and connection management for windsurf-teacher."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_DIR = Path.home() / ".windsurf-teacher"
DB_PATH = DB_DIR / "learnings.db"

_SCHEMA_VERSION = 1

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    project_path TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp TEXT NOT NULL,
    response_text TEXT NOT NULL,
    response_type TEXT NOT NULL DEFAULT 'raw'
);

CREATE TABLE IF NOT EXISTS code_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp TEXT NOT NULL,
    file_path TEXT NOT NULL,
    old_code TEXT,
    new_code TEXT,
    diff_summary TEXT
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    timestamp TEXT NOT NULL,
    command_line TEXT NOT NULL,
    working_dir TEXT
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id),
    timestamp TEXT NOT NULL,
    name TEXT NOT NULL,
    explanation TEXT NOT NULL,
    code_example TEXT DEFAULT '',
    tags TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'hook',
    reviewed_at TEXT,
    review_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 1,
    tags TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS gotchas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER REFERENCES concepts(id),
    description TEXT NOT NULL,
    code_example TEXT DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'warning'
);
"""

_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS concepts_fts USING fts5(
    name,
    explanation,
    tags,
    content='concepts',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS concepts_ai AFTER INSERT ON concepts BEGIN
    INSERT INTO concepts_fts(rowid, name, explanation, tags)
    VALUES (new.id, new.name, new.explanation, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS concepts_ad AFTER DELETE ON concepts BEGIN
    INSERT INTO concepts_fts(concepts_fts, rowid, name, explanation, tags)
    VALUES ('delete', old.id, old.name, old.explanation, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS concepts_au AFTER UPDATE ON concepts BEGIN
    INSERT INTO concepts_fts(concepts_fts, rowid, name, explanation, tags)
    VALUES ('delete', old.id, old.name, old.explanation, old.tags);
    INSERT INTO concepts_fts(rowid, name, explanation, tags)
    VALUES (new.id, new.name, new.explanation, new.tags);
END;
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_responses_session ON responses(session_id);
CREATE INDEX IF NOT EXISTS idx_code_changes_session ON code_changes(session_id);
CREATE INDEX IF NOT EXISTS idx_commands_session ON commands(session_id);
CREATE INDEX IF NOT EXISTS idx_concepts_session ON concepts(session_id);
CREATE INDEX IF NOT EXISTS idx_concepts_source ON concepts(source);
CREATE INDEX IF NOT EXISTS idx_concepts_reviewed_at ON concepts(reviewed_at);
CREATE INDEX IF NOT EXISTS idx_gotchas_concept ON gotchas(concept_id);
"""


def _init_db(conn: sqlite3.Connection) -> None:
    """Create tables, FTS5 indexes, and set schema version."""
    conn.executescript(_TABLES_SQL)
    conn.executescript(_FTS_SQL)
    conn.executescript(_INDEXES_SQL)

    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
        conn.commit()


def get_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a connection to the learning database, creating it if needed.

    Parameters
    ----------
    db_path:
        Override the default database path (useful for testing).

    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    _init_db(conn)
    return conn
