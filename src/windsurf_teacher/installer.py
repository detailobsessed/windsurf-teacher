"""Install/uninstall windsurf-teacher into Windsurf Next."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
WINDSURF_NEXT_DIR = Path.home() / ".codeium" / "windsurf-next"
SKILL_DIR = WINDSURF_NEXT_DIR / "skills" / "learn-mode"
HOOKS_CONFIG = WINDSURF_NEXT_DIR / "hooks.json"
MCP_CONFIG = WINDSURF_NEXT_DIR / "mcp_config.json"
DB_DIR = Path.home() / ".windsurf-teacher"

WORKFLOW_DIR = WINDSURF_NEXT_DIR / "global_workflows"
HOOK_EVENTS = ("post_cascade_response", "post_write_code", "post_run_command")
MCP_SERVER_NAME = "windsurf-teacher"


def _print(msg: str) -> None:
    print(msg)  # noqa: T201


def _python_path() -> str:
    """Resolve the project venv's python absolute path (cross-platform)."""
    if sys.platform == "win32":
        venv_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = PROJECT_DIR / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        msg = f"Venv python not found at {venv_python}. Run 'uv sync' first."
        raise FileNotFoundError(msg)
    return str(venv_python.resolve())


def _hooks_dir() -> str:
    """Resolve absolute path to the hooks directory."""
    return str((PROJECT_DIR / "src" / "windsurf_teacher" / "hooks").resolve())


def _build_hook_command() -> str:
    python = _python_path()
    script = str(Path(_hooks_dir()) / "capture_session.py")
    if sys.platform == "win32":
        return subprocess.list2cmdline([python, script])
    return f"{shlex.quote(python)} {shlex.quote(script)}"


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _install_skill() -> None:
    """Copy SKILL.md into the global skills directory."""
    source = PROJECT_DIR / "SKILL.md"
    if not source.exists():
        _print(f"  ⚠ SKILL.md not found at {source}")
        return
    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, SKILL_DIR / "SKILL.md")
    _print(f"  ✓ Skill installed to {SKILL_DIR}")


def _install_hooks() -> None:
    """Merge our hook entries into the user-level hooks.json."""
    config = _load_json(HOOKS_CONFIG)
    hooks = config.setdefault("hooks", {})
    command = _build_hook_command()

    hook_entry = {"command": command, "show_output": False}

    for event in HOOK_EVENTS:
        event_hooks = hooks.setdefault(event, [])
        if not any(h.get("command") == command for h in event_hooks):
            event_hooks.append(hook_entry)

    _save_json(HOOKS_CONFIG, config)
    _print(f"  ✓ Hooks installed to {HOOKS_CONFIG}")


def _install_mcp_server() -> None:
    """Register the MCP server in mcp_config.json."""
    config = _load_json(MCP_CONFIG)
    servers = config.setdefault("mcpServers", {})

    servers[MCP_SERVER_NAME] = {
        "command": "uv",
        "args": ["run", "--directory", str(PROJECT_DIR), "windsurf-teacher", "serve"],
    }

    _save_json(MCP_CONFIG, config)
    _print(f"  ✓ MCP server registered in {MCP_CONFIG}")


def _install_workflow() -> None:
    """Copy learn-review.md into the global workflows directory."""
    source = PROJECT_DIR / "learn-review.md"
    if not source.exists():
        _print(f"  ⚠ learn-review.md not found at {source}")
        return
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, WORKFLOW_DIR / "learn-review.md")
    _print(f"  ✓ Workflow installed to {WORKFLOW_DIR}")


def _create_db_dir() -> None:
    """Create the learning database directory."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    _print(f"  ✓ Database directory: {DB_DIR}")


def _uninstall_skill() -> None:
    """Remove the learn-mode skill directory."""
    if SKILL_DIR.exists():
        shutil.rmtree(SKILL_DIR)
        _print(f"  ✓ Removed skill: {SKILL_DIR}")
    else:
        _print("  - Skill not installed, skipping")


def _uninstall_hooks() -> None:
    """Remove our hook entries from hooks.json (leave other hooks intact)."""
    if not HOOKS_CONFIG.exists():
        _print("  - No hooks.json found, skipping")
        return

    config = _load_json(HOOKS_CONFIG)
    hooks = config.get("hooks", {})
    removed = False

    for event in HOOK_EVENTS:
        if event in hooks:
            original_len = len(hooks[event])
            hooks[event] = [h for h in hooks[event] if "capture_session.py" not in h.get("command", "")]
            if len(hooks[event]) < original_len:
                removed = True
            if not hooks[event]:
                del hooks[event]

    if removed:
        _save_json(HOOKS_CONFIG, config)
        _print(f"  ✓ Hooks removed from {HOOKS_CONFIG}")
    else:
        _print("  - No windsurf-teacher hooks found, skipping")


def _uninstall_mcp_server() -> None:
    """Remove our MCP server entry from mcp_config.json."""
    if not MCP_CONFIG.exists():
        _print("  - No mcp_config.json found, skipping")
        return

    config = _load_json(MCP_CONFIG)
    servers = config.get("mcpServers", {})

    if MCP_SERVER_NAME in servers:
        del servers[MCP_SERVER_NAME]
        _save_json(MCP_CONFIG, config)
        _print(f"  ✓ MCP server removed from {MCP_CONFIG}")
    else:
        _print("  - MCP server not registered, skipping")


def _uninstall_workflow() -> None:
    """Remove the learn-review workflow file."""
    workflow_file = WORKFLOW_DIR / "learn-review.md"
    if workflow_file.exists():
        workflow_file.unlink()
        _print(f"  ✓ Removed workflow: {workflow_file}")
    else:
        _print("  - Workflow not installed, skipping")


def run_install() -> None:
    """Install windsurf-teacher skill, hooks, and MCP server into Windsurf Next."""
    _print("Installing windsurf-teacher...")
    _install_skill()
    _install_hooks()
    _install_mcp_server()
    _install_workflow()
    _create_db_dir()
    _print("\nDone! Restart Windsurf to activate.")


def run_uninstall() -> None:
    """Uninstall windsurf-teacher from Windsurf Next."""
    _print("Uninstalling windsurf-teacher...")
    _uninstall_skill()
    _uninstall_hooks()
    _uninstall_mcp_server()
    _uninstall_workflow()

    if DB_DIR.exists():
        answer = input(f"\nDelete learning database at {DB_DIR}? [y/N] ").strip().lower()
        if answer == "y":
            shutil.rmtree(DB_DIR)
            _print(f"  ✓ Removed {DB_DIR}")
        else:
            _print(f"  - Kept {DB_DIR}")

    _print("\nDone! Restart Windsurf to deactivate.")
