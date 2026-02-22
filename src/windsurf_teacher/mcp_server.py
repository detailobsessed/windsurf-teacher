"""FastMCP server for windsurf-teacher.

Exposes tools that Cascade calls when in @learn-mode to log concepts,
patterns, gotchas, and query the learning database.
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastmcp import FastMCP

from windsurf_teacher.db import get_db

mcp = FastMCP("windsurf-teacher")

Severity = Literal["danger", "warning", "info"]

_MAX_EXPORT_CONCEPTS = 50
_MAX_EXPORT_PATTERNS = 50
_MAX_EXPORT_GOTCHAS = 50


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@mcp.tool
def log_concept(
    name: str,
    explanation: str,
    code_example: str = "",
    tags: list[str] | None = None,
) -> str:
    """Log a new concept learned during a coding session.

    Call this whenever the user learns something new. After logging, consider:
    - log_gotcha() to record common pitfalls related to this concept
    - log_pattern() if this concept is part of a recurring design pattern
    - query_concepts() to check if similar concepts already exist
    """
    with closing(get_db()) as conn:
        tags_str = ",".join(tags) if tags else ""
        cursor = conn.execute(
            "INSERT INTO concepts (timestamp, name, explanation, code_example, tags, source) VALUES (?, ?, ?, ?, ?, ?)",
            (_now_iso(), name, explanation, code_example, tags_str, "mcp"),
        )
        conn.commit()
        concept_id = cursor.lastrowid
        return (
            f"Concept '{name}' logged with id {concept_id}. "
            f"Next: call log_gotcha(concept_name='{name}') to add pitfalls, "
            f"or log_pattern() if this is a recurring pattern."
        )


@mcp.tool
def log_pattern(
    name: str,
    description: str,
    tags: list[str] | None = None,
) -> str:
    """Log a design or coding pattern. Increments times_seen if it already exists.

    Use this for recurring patterns observed across sessions (e.g. "factory",
    "dependency injection"). Safe to call multiple times with the same name.
    After logging, call get_stats() to see overall learning progress.
    """
    with closing(get_db()) as conn:
        row = conn.execute("SELECT id, times_seen FROM patterns WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                "UPDATE patterns SET times_seen = ?, description = ? WHERE id = ?",
                (row["times_seen"] + 1, description, row["id"]),
            )
            conn.commit()
            return f"Pattern '{name}' updated (seen {row['times_seen'] + 1} times)"

        tags_str = ",".join(tags) if tags else ""
        conn.execute(
            "INSERT INTO patterns (name, description, first_seen, tags) VALUES (?, ?, ?, ?)",
            (name, description, _now_iso(), tags_str),
        )
        conn.commit()
        return f"Pattern '{name}' logged. Next: call log_concept() to record related concepts."


@mcp.tool
def log_gotcha(
    description: str,
    code_example: str = "",
    severity: Severity = "warning",
    concept_name: str = "",
) -> str:
    """Log a common mistake or pitfall, optionally linked to a concept.

    Call this after log_concept() to record gotchas for a specific concept.
    Pass concept_name to link the gotcha; use query_concepts() first if unsure
    of the exact name. Severity must be 'danger', 'warning', or 'info'.
    """
    with closing(get_db()) as conn:
        concept_id = None
        warning = ""
        if concept_name:
            row = conn.execute(
                "SELECT id FROM concepts WHERE name = ? ORDER BY id DESC LIMIT 1",
                (concept_name,),
            ).fetchone()
            if row:
                concept_id = row["id"]
            else:
                warning = (
                    f" ⚠ Concept '{concept_name}' not found — gotcha saved unlinked. "
                    f"Call query_concepts(search='{concept_name}') to find the correct name."
                )

        conn.execute(
            "INSERT INTO gotchas (concept_id, description, code_example, severity) VALUES (?, ?, ?, ?)",
            (concept_id, description, code_example, severity),
        )
        conn.commit()
        return f"Gotcha logged (severity={severity}){warning}"


@mcp.tool
def query_concepts(
    search: str = "",
    tags: str = "",
    limit: int = 20,
) -> str:
    """Search concepts by text (FTS5) or tags. Returns recent concepts if no filters.

    Use this to find existing concepts before logging duplicates with log_concept(),
    or to look up concept names for log_gotcha(concept_name=...). Pass a search
    term for full-text search, or comma-separated tags to filter by tag.
    After finding gaps, call get_learning_gaps() to prioritize review.
    """
    with closing(get_db()) as conn:
        if search:
            rows = conn.execute(
                "SELECT c.id, c.name, c.explanation, c.tags, c.source, c.timestamp "
                "FROM concepts c JOIN concepts_fts f ON c.id = f.rowid "
                "WHERE concepts_fts MATCH ? ORDER BY c.timestamp DESC LIMIT ?",
                (search, limit),
            ).fetchall()
        elif tags:
            tag_list = [t.strip() for t in tags.split(",")]
            placeholders = " OR ".join("c.tags LIKE ?" for _ in tag_list)
            params = [f"%{t}%" for t in tag_list]
            params.append(limit)
            rows = conn.execute(
                f"SELECT c.id, c.name, c.explanation, c.tags, c.source, c.timestamp "  # noqa: S608
                f"FROM concepts c WHERE ({placeholders}) ORDER BY c.timestamp DESC LIMIT ?",
                params,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, explanation, tags, source, timestamp FROM concepts ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        if not rows:
            return "No concepts found. Call log_concept() to start logging."

        lines = []
        for r in rows:
            tags_display = f" [{r['tags']}]" if r["tags"] else ""
            lines.append(f"- **{r['name']}** (id={r['id']}){tags_display}: {r['explanation'][:120]}")
        return "\n".join(lines)


@mcp.tool
def get_learning_gaps(days: int = 7) -> str:
    """Return concepts not reviewed recently or with low review counts.

    Use this to find concepts that need reinforcement. Results are sorted by
    review count (least reviewed first). Call mark_reviewed(concept_id=...)
    after quizzing the user on a concept.
    Prerequisite: concepts must exist — call get_stats() first to check.
    """
    with closing(get_db()) as conn:
        cutoff = (datetime.now(tz=UTC) - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT id, name, explanation, tags, reviewed_at, review_count "
            "FROM concepts "
            "WHERE reviewed_at IS NULL OR reviewed_at < ? "
            "ORDER BY review_count ASC, timestamp DESC LIMIT 20",
            (cutoff,),
        ).fetchall()

        if not rows:
            return "No learning gaps found — you're up to date!"

        lines = []
        for r in rows:
            status = "never reviewed" if r["reviewed_at"] is None else f"last reviewed {r['reviewed_at'][:10]}"
            lines.append(f"- **{r['name']}** (id={r['id']}, {status}, reviewed {r['review_count']}x): {r['explanation'][:100]}")
        lines.append("\nNext: call mark_reviewed(concept_id=<id>) after the user answers correctly.")
        return "\n".join(lines)


@mcp.tool
def export_review_markdown(days: int = 7) -> str:
    """Generate a markdown review document for recent learnings.

    Produces a structured markdown summary of concepts, patterns, and gotchas.
    Results are capped to avoid excessive output. For a quick overview, call
    get_stats() instead. Use get_learning_gaps() to find concepts needing review.
    """
    with closing(get_db()) as conn:
        cutoff = (datetime.now(tz=UTC) - timedelta(days=days)).isoformat()

        sections = [f"# Learning Review — Last {days} Days\n"]

        total_concepts = conn.execute("SELECT count(*) FROM concepts WHERE timestamp > ?", (cutoff,)).fetchone()[0]
        concepts = conn.execute(
            "SELECT name, explanation, code_example, tags, source, timestamp "
            "FROM concepts WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, _MAX_EXPORT_CONCEPTS),
        ).fetchall()

        if concepts:
            header = f"## Concepts ({total_concepts})"
            if total_concepts > _MAX_EXPORT_CONCEPTS:
                header += f" — showing first {_MAX_EXPORT_CONCEPTS}"
            sections.append(f"{header}\n")
            for c in concepts:
                sections.extend((
                    f"### {c['name']}",
                    f"*{c['timestamp'][:10]}* | source: {c['source']}",
                ))
                if c["tags"]:
                    sections.append(f"Tags: {c['tags']}")
                sections.append(f"\n{c['explanation']}\n")
                if c["code_example"]:
                    sections.append(f"```\n{c['code_example']}\n```\n")

        total_patterns = conn.execute("SELECT count(*) FROM patterns").fetchone()[0]
        patterns = conn.execute(
            "SELECT name, description, times_seen, tags FROM patterns ORDER BY times_seen DESC LIMIT ?",
            (_MAX_EXPORT_PATTERNS,),
        ).fetchall()

        if patterns:
            header = f"## Patterns ({total_patterns})"
            if total_patterns > _MAX_EXPORT_PATTERNS:
                header += f" — showing first {_MAX_EXPORT_PATTERNS}"
            sections.append(f"{header}\n")
            sections.extend(f"- **{p['name']}** (seen {p['times_seen']}x): {p['description']}" for p in patterns)

        total_gotchas = conn.execute("SELECT count(*) FROM gotchas").fetchone()[0]
        gotchas = conn.execute(
            "SELECT g.description, g.code_example, g.severity, c.name as concept_name "
            "FROM gotchas g LEFT JOIN concepts c ON g.concept_id = c.id "
            "ORDER BY g.id DESC LIMIT ?",
            (_MAX_EXPORT_GOTCHAS,),
        ).fetchall()

        if gotchas:
            header = f"\n## Gotchas ({total_gotchas})"
            if total_gotchas > _MAX_EXPORT_GOTCHAS:
                header += f" — showing first {_MAX_EXPORT_GOTCHAS}"
            sections.append(f"{header}\n")
            for g in gotchas:
                icon = {"danger": "🔴", "warning": "🟡", "info": "🔵"}.get(g["severity"], "⚪")
                concept_ref = f" (re: {g['concept_name']})" if g["concept_name"] else ""
                sections.append(f"- {icon} {g['description']}{concept_ref}")

        return "\n".join(sections) if len(sections) > 1 else "No learnings found for this period."


@mcp.tool
def get_session_summary(session_id: str = "") -> str:
    """Get summary of a specific session or the most recent one.

    Shows activity counts and concepts learned. Omit session_id to get
    the latest session. For a database-wide overview, use get_stats().
    """
    with closing(get_db()) as conn:
        if session_id:
            session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        else:
            session = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()

        if not session:
            return "No sessions found."

        sid = session["id"]
        lines = [
            f"## Session: {sid}",
            f"Started: {session['started_at']}",
        ]
        if session["project_path"]:
            lines.append(f"Project: {session['project_path']}")
        if session["summary"]:
            lines.append(f"Summary: {session['summary']}")

        response_count = conn.execute("SELECT count(*) FROM responses WHERE session_id = ?", (sid,)).fetchone()[0]
        change_count = conn.execute("SELECT count(*) FROM code_changes WHERE session_id = ?", (sid,)).fetchone()[0]
        command_count = conn.execute("SELECT count(*) FROM commands WHERE session_id = ?", (sid,)).fetchone()[0]
        concept_count = conn.execute("SELECT count(*) FROM concepts WHERE session_id = ?", (sid,)).fetchone()[0]

        lines.append(
            f"\n**Activity**: {response_count} responses, {change_count} code changes, {command_count} commands, {concept_count} concepts"
        )

        concepts = conn.execute(
            "SELECT name, tags FROM concepts WHERE session_id = ? ORDER BY timestamp",
            (sid,),
        ).fetchall()
        if concepts:
            lines.append("\n**Concepts learned**:")
            for c in concepts:
                tag_str = f" [{c['tags']}]" if c["tags"] else ""
                lines.append(f"- {c['name']}{tag_str}")

        return "\n".join(lines)


@mcp.tool
def mark_reviewed(concept_id: int = 0, concept_name: str = "") -> str:
    """Mark a concept as reviewed, incrementing its review count.

    Call this after a user correctly answers a review question. Pass either
    concept_id (from get_learning_gaps or query_concepts) or concept_name.
    If both are provided, concept_id takes precedence.
    After marking, call get_learning_gaps() to find the next concept to review.
    """
    with closing(get_db()) as conn:
        if concept_id:
            row = conn.execute("SELECT id, name FROM concepts WHERE id = ?", (concept_id,)).fetchone()
        elif concept_name:
            row = conn.execute(
                "SELECT id, name FROM concepts WHERE name = ? ORDER BY id DESC LIMIT 1",
                (concept_name,),
            ).fetchone()
        else:
            return "Provide either concept_id or concept_name. Call query_concepts() to find concepts."

        if not row:
            identifier = f"id={concept_id}" if concept_id else f"name='{concept_name}'"
            return f"Concept {identifier} not found. Call query_concepts() to search."

        conn.execute(
            "UPDATE concepts SET reviewed_at = ?, review_count = review_count + 1 WHERE id = ?",
            (_now_iso(), row["id"]),
        )
        conn.commit()
        return f"✓ Marked **{row['name']}** as reviewed (concept {row['id']}). Call get_learning_gaps() to find the next concept to review."


@mcp.tool
def get_stats() -> str:
    """Get a summary of the learning database — counts of concepts, patterns, gotchas, and sessions.

    Call this first to understand what's in the database before using other tools.
    This is a read-only discovery tool with no side effects.
    """
    with closing(get_db()) as conn:
        concepts = conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
        reviewed = conn.execute("SELECT count(*) FROM concepts WHERE reviewed_at IS NOT NULL").fetchone()[0]
        patterns = conn.execute("SELECT count(*) FROM patterns").fetchone()[0]
        gotchas = conn.execute("SELECT count(*) FROM gotchas").fetchone()[0]
        sessions = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]

        lines = [
            "## Learning Database Stats",
            f"- **Concepts**: {concepts} ({reviewed} reviewed, {concepts - reviewed} pending)",
            f"- **Patterns**: {patterns}",
            f"- **Gotchas**: {gotchas}",
            f"- **Sessions**: {sessions}",
        ]

        if concepts and concepts > reviewed:
            lines.append("\nNext: call get_learning_gaps() to find concepts needing review.")
        elif concepts:
            lines.append("\nAll concepts reviewed! Call export_review_markdown() for a full summary.")
        else:
            lines.append("\nNo data yet. Call log_concept() to start logging.")

        return "\n".join(lines)
