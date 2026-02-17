"""FastMCP server for windsurf-teacher.

Exposes tools that Cascade calls when in @learn-mode to log concepts,
patterns, gotchas, and query the learning database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastmcp import FastMCP

from windsurf_teacher.db import get_db

mcp = FastMCP("windsurf-teacher")


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

    Cascade calls this when teaching something new.
    """
    conn = get_db()
    try:
        tags_str = ",".join(tags) if tags else ""
        cursor = conn.execute(
            "INSERT INTO concepts (timestamp, name, explanation, code_example, tags, source) VALUES (?, ?, ?, ?, ?, ?)",
            (_now_iso(), name, explanation, code_example, tags_str, "mcp"),
        )
        conn.commit()
        return f"Concept '{name}' logged with id {cursor.lastrowid}"
    finally:
        conn.close()


@mcp.tool
def log_pattern(
    name: str,
    description: str,
    tags: list[str] | None = None,
) -> str:
    """Log a design or coding pattern. Increments times_seen if it already exists."""
    conn = get_db()
    try:
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
        return f"Pattern '{name}' logged"
    finally:
        conn.close()


@mcp.tool
def log_gotcha(
    description: str,
    code_example: str = "",
    severity: str = "warning",
    concept_name: str = "",
) -> str:
    """Log a common mistake or pitfall, optionally linked to a concept."""
    conn = get_db()
    try:
        concept_id = None
        if concept_name:
            row = conn.execute(
                "SELECT id FROM concepts WHERE name = ? ORDER BY id DESC LIMIT 1",
                (concept_name,),
            ).fetchone()
            if row:
                concept_id = row["id"]

        conn.execute(
            "INSERT INTO gotchas (concept_id, description, code_example, severity) VALUES (?, ?, ?, ?)",
            (concept_id, description, code_example, severity),
        )
        conn.commit()
        return f"Gotcha logged (severity={severity})"
    finally:
        conn.close()


@mcp.tool
def query_concepts(
    search: str = "",
    tags: str = "",
    limit: int = 20,
) -> str:
    """Search concepts by text (FTS5) or tags. Returns recent concepts if no filters."""
    conn = get_db()
    try:
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
            return "No concepts found."

        lines = []
        for r in rows:
            tags_display = f" [{r['tags']}]" if r["tags"] else ""
            lines.append(f"- **{r['name']}**{tags_display}: {r['explanation'][:120]}")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool
def get_learning_gaps(days: int = 7) -> str:
    """Return concepts not reviewed recently or with low review counts."""
    conn = get_db()
    try:
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
            lines.append(f"- **{r['name']}** ({status}, reviewed {r['review_count']}x): {r['explanation'][:100]}")
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool
def export_review_markdown(days: int = 7) -> str:
    """Generate a markdown review document for recent learnings."""
    conn = get_db()
    try:
        cutoff = (datetime.now(tz=UTC) - timedelta(days=days)).isoformat()

        sections = [f"# Learning Review — Last {days} Days\n"]

        concepts = conn.execute(
            "SELECT name, explanation, code_example, tags, source, timestamp FROM concepts WHERE timestamp > ? ORDER BY timestamp DESC",
            (cutoff,),
        ).fetchall()

        if concepts:
            sections.append(f"## Concepts ({len(concepts)})\n")
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

        patterns = conn.execute(
            "SELECT name, description, times_seen, tags FROM patterns ORDER BY times_seen DESC",
        ).fetchall()

        if patterns:
            sections.append(f"## Patterns ({len(patterns)})\n")
            sections.extend(f"- **{p['name']}** (seen {p['times_seen']}x): {p['description']}" for p in patterns)

        gotchas = conn.execute(
            "SELECT g.description, g.code_example, g.severity, c.name as concept_name "
            "FROM gotchas g LEFT JOIN concepts c ON g.concept_id = c.id "
            "ORDER BY g.id DESC",
        ).fetchall()

        if gotchas:
            sections.append(f"\n## Gotchas ({len(gotchas)})\n")
            for g in gotchas:
                icon = {"danger": "🔴", "warning": "🟡", "info": "🔵"}.get(g["severity"], "⚪")
                concept_ref = f" (re: {g['concept_name']})" if g["concept_name"] else ""
                sections.append(f"- {icon} {g['description']}{concept_ref}")

        return "\n".join(sections) if len(sections) > 1 else "No learnings found for this period."
    finally:
        conn.close()


@mcp.tool
def get_session_summary(session_id: str = "") -> str:
    """Get summary of a specific session or the most recent one."""
    conn = get_db()
    try:
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
    finally:
        conn.close()
