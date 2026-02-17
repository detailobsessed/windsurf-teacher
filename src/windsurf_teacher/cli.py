"""CLI for windsurf-teacher.

Uses cyclopts (bundled with fastmcp) for the command-line interface.
"""

from __future__ import annotations

import operator
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cyclopts import App

from windsurf_teacher.db import get_db

app = App(name="windsurf-teacher", help="Windsurf but you learn as you code")


@app.command
def serve() -> None:
    """Start the MCP server (stdio transport, for Windsurf)."""
    from windsurf_teacher.mcp_server import mcp  # noqa: PLC0415

    mcp.run(transport="stdio")


@app.command
def export(*, days: int = 7, output: str = "") -> None:
    """Export recent learnings to markdown."""
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

        content = "\n".join(sections) if len(sections) > 1 else "No learnings found for this period."
    finally:
        conn.close()

    if output:
        Path(output).write_text(content, encoding="utf-8")
        _print(f"Exported to {output}")
    else:
        _print(content)


@app.command
def stats() -> None:
    """Show learning statistics."""
    conn = get_db()
    try:
        concept_count = conn.execute("SELECT count(*) FROM concepts").fetchone()[0]
        session_count = conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
        pattern_count = conn.execute("SELECT count(*) FROM patterns").fetchone()[0]
        gotcha_count = conn.execute("SELECT count(*) FROM gotchas").fetchone()[0]

        reviewed = conn.execute("SELECT count(*) FROM concepts WHERE reviewed_at IS NOT NULL").fetchone()[0]
        review_pct = (reviewed / concept_count * 100) if concept_count else 0

        _print(f"Sessions:  {session_count}")
        _print(f"Concepts:  {concept_count}")
        _print(f"Patterns:  {pattern_count}")
        _print(f"Gotchas:   {gotcha_count}")
        _print(f"Reviewed:  {reviewed}/{concept_count} ({review_pct:.0f}%)")

        tags_rows = conn.execute(
            "SELECT tags FROM concepts WHERE tags != ''",
        ).fetchall()
        if tags_rows:
            tag_counts: dict[str, int] = {}
            for row in tags_rows:
                for raw_tag in row["tags"].split(","):
                    stripped = raw_tag.strip()
                    if stripped:
                        tag_counts[stripped] = tag_counts.get(stripped, 0) + 1
            top_tags = sorted(tag_counts.items(), key=operator.itemgetter(1), reverse=True)[:10]
            _print(f"\nTop tags:  {', '.join(f'{t}({c})' for t, c in top_tags)}")
    finally:
        conn.close()


@app.command
def search(query: str) -> None:
    """Full-text search across concepts."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT c.name, c.explanation, c.tags "
            "FROM concepts c JOIN concepts_fts f ON c.id = f.rowid "
            "WHERE concepts_fts MATCH ? ORDER BY c.timestamp DESC LIMIT 20",
            (query,),
        ).fetchall()

        if not rows:
            _print("No concepts found.")
            return

        for r in rows:
            tags_display = f" [{r['tags']}]" if r["tags"] else ""
            _print(f"- {r['name']}{tags_display}: {r['explanation'][:120]}")
    finally:
        conn.close()


@app.command
def review() -> None:
    """Show concepts due for review (not reviewed in >3 days)."""
    conn = get_db()
    try:
        cutoff = (datetime.now(tz=UTC) - timedelta(days=3)).isoformat()
        rows = conn.execute(
            "SELECT name, explanation, reviewed_at, review_count "
            "FROM concepts "
            "WHERE reviewed_at IS NULL OR reviewed_at < ? "
            "ORDER BY review_count ASC, timestamp DESC LIMIT 20",
            (cutoff,),
        ).fetchall()

        if not rows:
            _print("No concepts due for review — you're up to date!")
            return

        for r in rows:
            status = "never reviewed" if r["reviewed_at"] is None else f"last reviewed {r['reviewed_at'][:10]}"
            _print(f"- {r['name']} ({status}, reviewed {r['review_count']}x): {r['explanation'][:100]}")
    finally:
        conn.close()


@app.command
def install() -> None:
    """Install windsurf-teacher into Windsurf Next."""
    from windsurf_teacher.installer import run_install  # noqa: PLC0415

    run_install()


@app.command
def uninstall() -> None:
    """Uninstall windsurf-teacher from Windsurf Next."""
    from windsurf_teacher.installer import run_uninstall  # noqa: PLC0415

    run_uninstall()


def _print(*args: object) -> None:
    """Print wrapper to keep ruff T20 suppression in one place."""
    print(*args)  # noqa: T201


def main() -> None:
    """Entry point for the windsurf-teacher CLI."""
    app(sys.argv[1:])
