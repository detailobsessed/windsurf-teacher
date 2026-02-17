# windsurf-teacher

[![ci](https://github.com/detailobsessed/windsurf-teacher/workflows/ci/badge.svg)](https://github.com/detailobsessed/windsurf-teacher/actions?query=workflow%3Aci)
[![release](https://github.com/detailobsessed/windsurf-teacher/workflows/release/badge.svg)](https://github.com/detailobsessed/windsurf-teacher/actions?query=workflow%3Arelease)
[![documentation](https://img.shields.io/badge/docs-mkdocs-708FCC.svg?style=flat)](https://detailobsessed.github.io/windsurf-teacher/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/gh/detailobsessed/windsurf-teacher/branch/main/graph/badge.svg)](https://codecov.io/gh/detailobsessed/windsurf-teacher)

**Learn as you vibe-engineer.** Instead of blindly accepting AI-generated code, windsurf-teacher makes Cascade explain everything it does, captures session logs via hooks, stores structured learning data in SQLite, and provides an MCP server so Cascade can actively log concepts during sessions.

## How it works

```text
coding sessions → hooks capture responses/diffs → SQLite stores structured learnings
                                                 → export to markdown → NotebookLM flashcards
```

- **Skill** (`@learn-mode`) — changes Cascade's behavior to explain before writing, annotate code with `# LEARN:` comments, and summarize patterns
- **Hooks** — silently capture every Cascade response, code edit, and command to SQLite
- **MCP server** — Cascade calls tools like `log_concept`, `log_pattern`, `log_gotcha` when teaching
- **CLI** — review, export, and search your learnings outside of Windsurf

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- [Windsurf Next](https://windsurf.com)

## Installation

```bash
# Clone and set up
git clone https://github.com/detailobsessed/windsurf-teacher.git
cd windsurf-teacher
uv sync

# Install into Windsurf Next (skill, hooks, MCP server)
uv run windsurf-teacher install
```

This installs:

1. The `learn-mode` skill into `~/.codeium/windsurf-next/skills/learn-mode/`
2. Hook entries into `~/.codeium/windsurf-next/hooks.json` (merged with existing hooks)
3. The MCP server into `~/.codeium/windsurf-next/mcp_config.json`
4. The learning database directory at `~/.windsurf-teacher/`

Restart Windsurf after installing.

## Usage

### In Windsurf

Activate the skill by typing `@learn-mode` in Cascade. Cascade will:

- Explain what it's about to do and why before writing code
- Add `# LEARN:` comments on non-obvious lines
- Log concepts, patterns, and gotchas to the database via MCP tools
- Summarize what you should know after each task
- Ask one comprehension question

### CLI

```bash
# Show learning statistics
windsurf-teacher stats

# Full-text search across concepts
windsurf-teacher search "context manager"

# Show concepts due for review (not reviewed in >3 days)
windsurf-teacher review

# Export recent learnings to markdown (for NotebookLM)
windsurf-teacher export --days 7 --output review.md

# Start the MCP server manually (usually not needed)
windsurf-teacher serve
```

### Global workflow

Copy `learn-review.md` to `~/.codeium/windsurf-next/global_workflows/` to add a `/learn-review` command that quizzes you on recent concepts.

## Uninstalling

```bash
uv run windsurf-teacher uninstall
```

This removes the skill, hooks, and MCP server entries (leaving other hooks/servers intact). You'll be asked whether to delete the learning database.

## Development

```bash
uv sync                  # Install all dependencies
uv run poe check         # Lint + typecheck
uv run poe test          # Run tests
uv run poe test-cov      # Tests with coverage
```

## Architecture

```text
src/windsurf_teacher/
├── db.py                 # SQLite schema (7 tables + FTS5), get_db()
├── hooks/
│   └── capture_session.py  # Hook handler (stdin JSON → SQLite)
├── mcp_server.py         # FastMCP v3 server (7 tools)
├── cli.py                # CLI (cyclopts)
└── installer.py          # Install/uninstall logic

install.py                # Root-level install script
uninstall.py              # Root-level uninstall script
hooks.json                # Hook template with placeholders
SKILL.md                  # Learn-mode skill definition
learn-review.md           # Global workflow for review quizzes
```
