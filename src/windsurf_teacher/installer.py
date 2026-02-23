"""Install/uninstall windsurf-teacher into Windsurf editions."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
DB_DIR = Path.home() / ".windsurf-teacher"

HOOK_EVENTS = ("post_cascade_response", "post_write_code", "post_run_command")
MCP_SERVER_NAME = "windsurf-teacher"

EDITIONS: dict[str, str] = {
    "windsurf": "Windsurf (stable)",
    "windsurf-next": "Windsurf Next (beta)",
    "windsurf-insiders": "Windsurf Insiders",
}

APP_BUNDLES: dict[str, str] = {
    "windsurf": "Windsurf.app",
    "windsurf-next": "Windsurf - Next.app",
    "windsurf-insiders": "Windsurf - Insiders.app",
}


@dataclass(frozen=True)
class EditionPaths:
    """Resolved paths for a single Windsurf edition."""

    name: str
    label: str
    base_dir: Path
    skill_dir: Path
    hooks_config: Path
    mcp_config: Path
    workflow_dir: Path

    @classmethod
    def for_edition(cls, edition: str, *, codeium_base: Path | None = None) -> EditionPaths:
        base = (codeium_base or Path.home() / ".codeium") / edition
        label = EDITIONS.get(edition, edition)
        return cls(
            name=edition,
            label=label,
            base_dir=base,
            skill_dir=base / "skills" / "learn-mode",
            hooks_config=base / "hooks.json",
            mcp_config=base / "mcp_config.json",
            workflow_dir=base / "global_workflows",
        )


def _codeium_base() -> Path:
    return Path.home() / ".codeium"


def _applications_dir() -> Path:
    return Path("/Applications")


def _is_app_installed(edition: str) -> bool:
    """Check whether the Windsurf app bundle exists for *edition*.

    On non-macOS platforms the check is skipped (returns ``True``).
    """
    if sys.platform != "darwin":
        return True
    bundle = APP_BUNDLES.get(edition)
    if not bundle:
        return True
    return (_applications_dir() / bundle).is_dir()


def detect_editions(*, codeium_base: Path | None = None) -> list[EditionPaths]:
    """Return EditionPaths for every Windsurf edition found on disk."""
    base = codeium_base or _codeium_base()
    return [EditionPaths.for_edition(name, codeium_base=base) for name in EDITIONS if (base / name).is_dir() and _is_app_installed(name)]


def _prompt_editions(detected: list[EditionPaths]) -> list[EditionPaths]:
    """Interactively ask the user which edition(s) to target."""
    if len(detected) == 1:
        _print(f"  Found: {detected[0].label}")
        return detected

    _print("  Detected Windsurf editions:")
    for i, ed in enumerate(detected, 1):
        _print(f"    {i}. {ed.label}")
    _print(f"    a. All ({len(detected)} editions)")

    while True:
        answer = input(f"  Select edition [1-{len(detected)}, a]: ").strip().lower()
        if answer == "a":
            return detected
        if answer.isdigit() and 1 <= int(answer) <= len(detected):
            return [detected[int(answer) - 1]]
        _print(f"  Invalid choice. Enter 1-{len(detected)} or 'a'.")


def resolve_editions(edition: str = "") -> list[EditionPaths]:
    """Resolve which edition(s) to target, with optional CLI override.

    If *edition* is given (e.g. ``--edition windsurf-next`` or ``--edition all``),
    use that directly.  Otherwise auto-detect and prompt interactively.
    """
    detected = detect_editions()
    if not detected:
        _print("  ⚠ No Windsurf editions found in ~/.codeium/")
        _print("  Expected one of: windsurf, windsurf-next, windsurf-insiders")
        return []

    if edition == "all":
        return detected
    if edition:
        match = [ed for ed in detected if ed.name == edition]
        if not match:
            valid = ", ".join(ed.name for ed in detected)
            _print(f"  ⚠ Edition '{edition}' not found. Available: {valid}")
            return []
        return match

    return _prompt_editions(detected)


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
    return str(venv_python)


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


def _install_skill(paths: EditionPaths) -> None:
    """Copy SKILL.md into the global skills directory."""
    source = PROJECT_DIR / "SKILL.md"
    if not source.exists():
        _print(f"  ⚠ SKILL.md not found at {source}")
        return
    paths.skill_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, paths.skill_dir / "SKILL.md")
    _print(f"  ✓ Skill installed to {paths.skill_dir}")


def _install_hooks(paths: EditionPaths) -> None:
    """Merge our hook entries into the user-level hooks.json."""
    config = _load_json(paths.hooks_config)
    hooks = config.setdefault("hooks", {})
    command = _build_hook_command()

    hook_entry = {"command": command, "show_output": False}

    for event in HOOK_EVENTS:
        event_hooks = hooks.setdefault(event, [])
        if not any(h.get("command") == command for h in event_hooks):
            event_hooks.append(hook_entry)

    _save_json(paths.hooks_config, config)
    _print(f"  ✓ Hooks installed to {paths.hooks_config}")


def _install_mcp_server(paths: EditionPaths) -> None:
    """Register the MCP server in mcp_config.json."""
    config = _load_json(paths.mcp_config)
    servers = config.setdefault("mcpServers", {})

    servers[MCP_SERVER_NAME] = {
        "command": "uv",
        "args": ["run", "--directory", str(PROJECT_DIR), "windsurf-teacher", "serve"],
    }

    _save_json(paths.mcp_config, config)
    _print(f"  ✓ MCP server registered in {paths.mcp_config}")


def _install_workflow(paths: EditionPaths) -> None:
    """Copy learn-review.md into the global workflows directory."""
    source = PROJECT_DIR / "learn-review.md"
    if not source.exists():
        _print(f"  ⚠ learn-review.md not found at {source}")
        return
    paths.workflow_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, paths.workflow_dir / "learn-review.md")
    _print(f"  ✓ Workflow installed to {paths.workflow_dir}")


def _create_db_dir() -> None:
    """Create the learning database directory."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    _print(f"  ✓ Database directory: {DB_DIR}")


def _uninstall_skill(paths: EditionPaths) -> None:
    """Remove the learn-mode skill directory."""
    if paths.skill_dir.exists():
        shutil.rmtree(paths.skill_dir)
        _print(f"  ✓ Removed skill: {paths.skill_dir}")
    else:
        _print("  - Skill not installed, skipping")


def _uninstall_hooks(paths: EditionPaths) -> None:
    """Remove our hook entries from hooks.json (leave other hooks intact)."""
    if not paths.hooks_config.exists():
        _print("  - No hooks.json found, skipping")
        return

    config = _load_json(paths.hooks_config)
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
        _save_json(paths.hooks_config, config)
        _print(f"  ✓ Hooks removed from {paths.hooks_config}")
    else:
        _print("  - No windsurf-teacher hooks found, skipping")


def _uninstall_mcp_server(paths: EditionPaths) -> None:
    """Remove our MCP server entry from mcp_config.json."""
    if not paths.mcp_config.exists():
        _print("  - No mcp_config.json found, skipping")
        return

    config = _load_json(paths.mcp_config)
    servers = config.get("mcpServers", {})

    if MCP_SERVER_NAME in servers:
        del servers[MCP_SERVER_NAME]
        _save_json(paths.mcp_config, config)
        _print(f"  ✓ MCP server removed from {paths.mcp_config}")
    else:
        _print("  - MCP server not registered, skipping")


def _uninstall_workflow(paths: EditionPaths) -> None:
    """Remove the learn-review workflow file."""
    workflow_file = paths.workflow_dir / "learn-review.md"
    if workflow_file.exists():
        workflow_file.unlink()
        _print(f"  ✓ Removed workflow: {workflow_file}")
    else:
        _print("  - Workflow not installed, skipping")


def _install_to_edition(paths: EditionPaths) -> None:
    """Install all components into a single edition."""
    _install_skill(paths)
    _install_hooks(paths)
    _install_mcp_server(paths)
    _install_workflow(paths)


def _uninstall_from_edition(paths: EditionPaths) -> None:
    """Uninstall all components from a single edition."""
    _uninstall_skill(paths)
    _uninstall_hooks(paths)
    _uninstall_mcp_server(paths)
    _uninstall_workflow(paths)


def run_install(edition: str = "") -> None:
    """Install windsurf-teacher into one or more Windsurf editions."""
    _print("Installing windsurf-teacher...")
    editions = resolve_editions(edition)
    if not editions:
        return

    for ed in editions:
        if len(editions) > 1:
            _print(f"\n  [{ed.label}]")
        _install_to_edition(ed)

    _create_db_dir()
    names = ", ".join(ed.label for ed in editions)
    _print(f"\nDone! Restart {names} to activate.")


def run_uninstall(edition: str = "") -> None:
    """Uninstall windsurf-teacher from one or more Windsurf editions."""
    _print("Uninstalling windsurf-teacher...")
    editions = resolve_editions(edition)
    if not editions:
        return

    for ed in editions:
        if len(editions) > 1:
            _print(f"\n  [{ed.label}]")
        _uninstall_from_edition(ed)

    if DB_DIR.exists():
        answer = input(f"\nDelete learning database at {DB_DIR}? [y/N] ").strip().lower()
        if answer == "y":
            shutil.rmtree(DB_DIR)
            _print(f"  ✓ Removed {DB_DIR}")
        else:
            _print(f"  - Kept {DB_DIR}")

    names = ", ".join(ed.label for ed in editions)
    _print(f"\nDone! Restart {names} to deactivate.")
