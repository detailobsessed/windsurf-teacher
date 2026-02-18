"""Tests for windsurf_teacher.installer module."""

from __future__ import annotations

import json

import pytest

from windsurf_teacher.installer import (
    HOOK_EVENTS,
    MCP_SERVER_NAME,
    _install_hooks,
    _install_mcp_server,
    _install_skill,
    _install_workflow,
    _load_json,
    _save_json,
    _uninstall_hooks,
    _uninstall_mcp_server,
    _uninstall_skill,
    _uninstall_workflow,
    run_install,
    run_uninstall,
)


@pytest.fixture
def _patch_paths(tmp_path, monkeypatch):
    """Redirect all installer paths to tmp_path."""
    monkeypatch.setattr("windsurf_teacher.installer.WINDSURF_NEXT_DIR", tmp_path / "windsurf-next")
    monkeypatch.setattr("windsurf_teacher.installer.SKILL_DIR", tmp_path / "windsurf-next" / "skills" / "learn-mode")
    monkeypatch.setattr("windsurf_teacher.installer.HOOKS_CONFIG", tmp_path / "windsurf-next" / "hooks.json")
    monkeypatch.setattr("windsurf_teacher.installer.MCP_CONFIG", tmp_path / "windsurf-next" / "mcp_config.json")
    monkeypatch.setattr("windsurf_teacher.installer.DB_DIR", tmp_path / "db")
    monkeypatch.setattr("windsurf_teacher.installer.WORKFLOW_DIR", tmp_path / "windsurf-next" / "global_workflows")


class TestJsonHelpers:
    def test_load_json_missing_file(self, tmp_path):
        result = _load_json(tmp_path / "missing.json")
        assert result == {}

    def test_load_json_existing_file(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"key": "value"}', encoding="utf-8")
        result = _load_json(path)
        assert result == {"key": "value"}

    def test_save_json_creates_parents(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "test.json"
        _save_json(path, {"hello": "world"})
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == {"hello": "world"}


@pytest.mark.usefixtures("_patch_paths")
class TestInstallSkill:
    def test_copies_skill_md(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "SKILL.md").write_text("# test skill", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_skill()
        skill_path = tmp_path / "windsurf-next" / "skills" / "learn-mode" / "SKILL.md"
        assert skill_path.exists()
        assert skill_path.read_text(encoding="utf-8") == "# test skill"

    def test_warns_if_skill_missing(self, tmp_path, monkeypatch, capsys):
        project_dir = tmp_path / "empty-project"
        project_dir.mkdir()
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_skill()
        assert "not found" in capsys.readouterr().out


@pytest.mark.usefixtures("_patch_paths")
class TestInstallHooks:
    def test_adds_hook_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        _install_hooks()
        hooks_path = tmp_path / "windsurf-next" / "hooks.json"
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        for event in HOOK_EVENTS:
            assert event in config["hooks"]
            assert any(h["command"] == "/usr/bin/python capture.py" for h in config["hooks"][event])

    def test_idempotent_install(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        _install_hooks()
        _install_hooks()
        hooks_path = tmp_path / "windsurf-next" / "hooks.json"
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        for event in HOOK_EVENTS:
            assert len(config["hooks"][event]) == 1

    def test_preserves_existing_hooks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        hooks_path = tmp_path / "windsurf-next" / "hooks.json"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        hooks_path.write_text(
            json.dumps({"hooks": {"post_cascade_response": [{"command": "other-tool", "show_output": True}]}}), encoding="utf-8"
        )

        _install_hooks()
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        assert len(config["hooks"]["post_cascade_response"]) == 2


@pytest.mark.usefixtures("_patch_paths")
class TestInstallMcpServer:
    def test_registers_server(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", tmp_path / "project")

        _install_mcp_server()
        mcp_path = tmp_path / "windsurf-next" / "mcp_config.json"
        config = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert MCP_SERVER_NAME in config["mcpServers"]
        assert config["mcpServers"][MCP_SERVER_NAME]["command"] == "uv"


@pytest.mark.usefixtures("_patch_paths")
class TestUninstallSkill:
    def test_removes_skill_dir(self, tmp_path):
        skill_dir = tmp_path / "windsurf-next" / "skills" / "learn-mode"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("test", encoding="utf-8")

        _uninstall_skill()
        assert not skill_dir.exists()

    def test_no_error_if_missing(self, capsys):
        _uninstall_skill()
        assert "not installed" in capsys.readouterr().out


@pytest.mark.usefixtures("_patch_paths")
class TestUninstallHooks:
    def test_removes_our_hooks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        hooks_path = tmp_path / "windsurf-next" / "hooks.json"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        hooks_path.write_text(
            json.dumps({
                "hooks": {
                    "post_cascade_response": [
                        {"command": "/usr/bin/python capture_session.py"},
                        {"command": "other-tool"},
                    ],
                }
            }),
            encoding="utf-8",
        )

        _uninstall_hooks()
        config = json.loads(hooks_path.read_text(encoding="utf-8"))
        assert len(config["hooks"]["post_cascade_response"]) == 1
        assert config["hooks"]["post_cascade_response"][0]["command"] == "other-tool"

    def test_no_error_if_no_hooks_json(self, capsys):
        _uninstall_hooks()
        assert "No hooks.json" in capsys.readouterr().out


@pytest.mark.usefixtures("_patch_paths")
class TestUninstallMcpServer:
    def test_removes_server_entry(self, tmp_path):
        mcp_path = tmp_path / "windsurf-next" / "mcp_config.json"
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(
            json.dumps({"mcpServers": {MCP_SERVER_NAME: {"command": "uv"}, "other": {"command": "node"}}}), encoding="utf-8"
        )

        _uninstall_mcp_server()
        config = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert MCP_SERVER_NAME not in config["mcpServers"]
        assert "other" in config["mcpServers"]

    def test_no_error_if_no_config(self, capsys):
        _uninstall_mcp_server()
        assert "No mcp_config.json" in capsys.readouterr().out


@pytest.mark.usefixtures("_patch_paths")
class TestRunInstall:
    def test_full_install(self, tmp_path, monkeypatch, capsys):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "SKILL.md").write_text("# skill", encoding="utf-8")
        (project_dir / "learn-review.md").write_text("---\ndescription: test\n---", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "python capture.py")

        run_install()
        out = capsys.readouterr().out
        assert "Installing" in out
        assert "Done" in out
        assert (tmp_path / "db").exists()


@pytest.mark.usefixtures("_patch_paths")
class TestRunUninstall:
    def test_full_uninstall_keep_db(self, tmp_path, monkeypatch, capsys):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        monkeypatch.setattr("builtins.input", lambda _: "n")

        run_uninstall()
        out = capsys.readouterr().out
        assert "Uninstalling" in out
        assert "Kept" in out
        assert db_dir.exists()

    def test_full_uninstall_delete_db(self, tmp_path, monkeypatch, capsys):
        db_dir = tmp_path / "db"
        db_dir.mkdir()
        monkeypatch.setattr("builtins.input", lambda _: "y")

        run_uninstall()
        out = capsys.readouterr().out
        assert "Removed" in out
        assert not db_dir.exists()

    def test_uninstall_no_db(self, capsys):
        run_uninstall()
        out = capsys.readouterr().out
        assert "Done" in out


@pytest.mark.usefixtures("_patch_paths")
class TestInstallWorkflow:
    def test_copies_workflow(self, tmp_path, monkeypatch, capsys):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "learn-review.md").write_text("---\ndescription: test\n---", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_workflow()
        out = capsys.readouterr().out
        assert "Workflow installed" in out
        assert (tmp_path / "windsurf-next" / "global_workflows" / "learn-review.md").exists()

    def test_warns_if_workflow_missing(self, tmp_path, monkeypatch, capsys):
        project_dir = tmp_path / "empty-project"
        project_dir.mkdir()
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_workflow()
        out = capsys.readouterr().out
        assert "⚠" in out


@pytest.mark.usefixtures("_patch_paths")
class TestUninstallWorkflow:
    def test_removes_workflow(self, tmp_path, capsys):
        wf_dir = tmp_path / "windsurf-next" / "global_workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "learn-review.md").write_text("test", encoding="utf-8")

        _uninstall_workflow()
        out = capsys.readouterr().out
        assert "Removed workflow" in out
        assert not (wf_dir / "learn-review.md").exists()

    def test_no_error_if_missing(self, capsys):
        _uninstall_workflow()
        out = capsys.readouterr().out
        assert "not installed" in out
