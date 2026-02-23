"""Tests for windsurf_teacher.installer module."""

from __future__ import annotations

import json

import pytest

from windsurf_teacher.installer import (
    HOOK_EVENTS,
    MCP_SERVER_NAME,
    EditionPaths,
    _install_hooks,
    _install_mcp_server,
    _install_skill,
    _install_workflow,
    _is_app_installed,
    _load_json,
    _prompt_editions,
    _save_json,
    _uninstall_hooks,
    _uninstall_mcp_server,
    _uninstall_skill,
    _uninstall_workflow,
    detect_editions,
    resolve_editions,
    run_install,
    run_uninstall,
)


@pytest.fixture
def edition_paths(tmp_path) -> EditionPaths:
    """Create an EditionPaths pointing at tmp_path."""
    return EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path)


@pytest.fixture
def _patch_detect_single(tmp_path, monkeypatch, edition_paths):
    """Make detect_editions return a single tmp edition (no prompt needed)."""
    monkeypatch.setattr("windsurf_teacher.installer.DB_DIR", tmp_path / "db")
    monkeypatch.setattr(
        "windsurf_teacher.installer.detect_editions",
        lambda **_kw: [edition_paths],
    )


class TestEditionPaths:
    def test_for_edition_paths(self, tmp_path):
        paths = EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path)
        assert paths.name == "windsurf-next"
        assert paths.label == "Windsurf Next (beta)"
        assert paths.base_dir == tmp_path / "windsurf-next"
        assert paths.skill_dir == tmp_path / "windsurf-next" / "skills" / "learn-mode"
        assert paths.hooks_config == tmp_path / "windsurf-next" / "hooks.json"
        assert paths.mcp_config == tmp_path / "windsurf-next" / "mcp_config.json"
        assert paths.workflow_dir == tmp_path / "windsurf-next" / "global_workflows"

    def test_unknown_edition_uses_name_as_label(self, tmp_path):
        paths = EditionPaths.for_edition("windsurf-custom", codeium_base=tmp_path)
        assert paths.label == "windsurf-custom"


class TestIsAppInstalled:
    def test_returns_true_when_bundle_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._applications_dir", lambda: tmp_path)
        monkeypatch.setattr("windsurf_teacher.installer.sys", type("FakeSys", (), {"platform": "darwin"})())
        (tmp_path / "Windsurf - Next.app").mkdir()
        assert _is_app_installed("windsurf-next") is True

    def test_returns_false_when_bundle_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._applications_dir", lambda: tmp_path)
        monkeypatch.setattr("windsurf_teacher.installer.sys", type("FakeSys", (), {"platform": "darwin"})())
        assert _is_app_installed("windsurf") is False

    def test_skipped_on_non_darwin(self, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer.sys", type("FakeSys", (), {"platform": "linux"})())
        assert _is_app_installed("windsurf") is True

    def test_unknown_edition_returns_true(self, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer.sys", type("FakeSys", (), {"platform": "darwin"})())
        assert _is_app_installed("windsurf-custom") is True


class TestDetectEditions:
    def test_detects_existing_editions(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._is_app_installed", lambda _: True)
        (tmp_path / "windsurf").mkdir()
        (tmp_path / "windsurf-next").mkdir()
        editions = detect_editions(codeium_base=tmp_path)
        assert len(editions) == 2
        names = {ed.name for ed in editions}
        assert names == {"windsurf", "windsurf-next"}

    def test_returns_empty_when_none_found(self, tmp_path):
        assert detect_editions(codeium_base=tmp_path) == []

    def test_ignores_unknown_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._is_app_installed", lambda _: True)
        (tmp_path / "windsurf-next").mkdir()
        (tmp_path / "random-other").mkdir()
        editions = detect_editions(codeium_base=tmp_path)
        assert len(editions) == 1
        assert editions[0].name == "windsurf-next"

    def test_skips_edition_without_app(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "windsurf_teacher.installer._is_app_installed",
            lambda name: name != "windsurf",
        )
        (tmp_path / "windsurf").mkdir()
        (tmp_path / "windsurf-next").mkdir()
        editions = detect_editions(codeium_base=tmp_path)
        assert len(editions) == 1
        assert editions[0].name == "windsurf-next"

    def test_config_dir_without_app_not_detected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("windsurf_teacher.installer._is_app_installed", lambda _: False)
        (tmp_path / "windsurf").mkdir()
        (tmp_path / "windsurf-next").mkdir()
        assert detect_editions(codeium_base=tmp_path) == []


class TestPromptEditions:
    def test_single_edition_no_prompt(self, tmp_path, capsys):
        editions = [EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path)]
        result = _prompt_editions(editions)
        assert result == editions
        assert "Found:" in capsys.readouterr().out

    def test_select_by_number(self, tmp_path, monkeypatch):
        editions = [
            EditionPaths.for_edition("windsurf", codeium_base=tmp_path),
            EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path),
        ]
        monkeypatch.setattr("builtins.input", lambda _: "2")
        result = _prompt_editions(editions)
        assert len(result) == 1
        assert result[0].name == "windsurf-next"

    def test_select_all(self, tmp_path, monkeypatch):
        editions = [
            EditionPaths.for_edition("windsurf", codeium_base=tmp_path),
            EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path),
        ]
        monkeypatch.setattr("builtins.input", lambda _: "a")
        result = _prompt_editions(editions)
        assert result == editions

    def test_invalid_then_valid(self, tmp_path, monkeypatch, capsys):
        editions = [
            EditionPaths.for_edition("windsurf", codeium_base=tmp_path),
            EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path),
        ]
        answers = iter(["x", "1"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        result = _prompt_editions(editions)
        assert len(result) == 1
        assert result[0].name == "windsurf"
        assert "Invalid choice" in capsys.readouterr().out


class TestResolveEditions:
    def test_resolve_specific_edition(self, tmp_path, monkeypatch):
        (tmp_path / "windsurf").mkdir()
        (tmp_path / "windsurf-next").mkdir()
        monkeypatch.setattr("windsurf_teacher.installer._codeium_base", lambda: tmp_path)
        monkeypatch.setattr("windsurf_teacher.installer._is_app_installed", lambda _: True)

        result = resolve_editions("windsurf-next")
        assert len(result) == 1
        assert result[0].name == "windsurf-next"

    def test_resolve_all(self, tmp_path, monkeypatch):
        (tmp_path / "windsurf").mkdir()
        (tmp_path / "windsurf-next").mkdir()
        (tmp_path / "windsurf-insiders").mkdir()
        monkeypatch.setattr("windsurf_teacher.installer._codeium_base", lambda: tmp_path)
        monkeypatch.setattr("windsurf_teacher.installer._is_app_installed", lambda _: True)

        result = resolve_editions("all")
        assert len(result) == 3

    def test_resolve_invalid_edition(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "windsurf-next").mkdir()
        monkeypatch.setattr("windsurf_teacher.installer._codeium_base", lambda: tmp_path)
        monkeypatch.setattr("windsurf_teacher.installer._is_app_installed", lambda _: True)

        result = resolve_editions("windsurf-bogus")
        assert result == []
        assert "not found" in capsys.readouterr().out

    def test_resolve_none_detected(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("windsurf_teacher.installer._codeium_base", lambda: tmp_path)

        result = resolve_editions()
        assert result == []
        assert "No Windsurf editions" in capsys.readouterr().out


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


class TestInstallSkill:
    def test_copies_skill_md(self, tmp_path, monkeypatch, edition_paths):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "SKILL.md").write_text("# test skill", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_skill(edition_paths)
        skill_path = edition_paths.skill_dir / "SKILL.md"
        assert skill_path.exists()
        assert skill_path.read_text(encoding="utf-8") == "# test skill"

    def test_warns_if_skill_missing(self, tmp_path, monkeypatch, edition_paths, capsys):
        project_dir = tmp_path / "empty-project"
        project_dir.mkdir()
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_skill(edition_paths)
        assert "not found" in capsys.readouterr().out


class TestInstallHooks:
    def test_adds_hook_entries(self, monkeypatch, edition_paths):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        _install_hooks(edition_paths)
        config = json.loads(edition_paths.hooks_config.read_text(encoding="utf-8"))
        for event in HOOK_EVENTS:
            assert event in config["hooks"]
            assert any(h["command"] == "/usr/bin/python capture.py" for h in config["hooks"][event])

    def test_idempotent_install(self, monkeypatch, edition_paths):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        _install_hooks(edition_paths)
        _install_hooks(edition_paths)
        config = json.loads(edition_paths.hooks_config.read_text(encoding="utf-8"))
        for event in HOOK_EVENTS:
            assert len(config["hooks"][event]) == 1

    def test_preserves_existing_hooks(self, monkeypatch, edition_paths):
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "/usr/bin/python capture.py")

        edition_paths.hooks_config.parent.mkdir(parents=True, exist_ok=True)
        edition_paths.hooks_config.write_text(
            json.dumps({"hooks": {"post_cascade_response": [{"command": "other-tool", "show_output": True}]}}),
            encoding="utf-8",
        )

        _install_hooks(edition_paths)
        config = json.loads(edition_paths.hooks_config.read_text(encoding="utf-8"))
        assert len(config["hooks"]["post_cascade_response"]) == 2


class TestInstallMcpServer:
    def test_registers_server(self, tmp_path, monkeypatch, edition_paths):
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", tmp_path / "project")

        _install_mcp_server(edition_paths)
        config = json.loads(edition_paths.mcp_config.read_text(encoding="utf-8"))
        assert MCP_SERVER_NAME in config["mcpServers"]
        assert config["mcpServers"][MCP_SERVER_NAME]["command"] == "uv"


class TestUninstallSkill:
    def test_removes_skill_dir(self, edition_paths):
        edition_paths.skill_dir.mkdir(parents=True)
        (edition_paths.skill_dir / "SKILL.md").write_text("test", encoding="utf-8")

        _uninstall_skill(edition_paths)
        assert not edition_paths.skill_dir.exists()

    def test_no_error_if_missing(self, edition_paths, capsys):
        _uninstall_skill(edition_paths)
        assert "not installed" in capsys.readouterr().out


class TestUninstallHooks:
    def test_removes_our_hooks(self, edition_paths):
        edition_paths.hooks_config.parent.mkdir(parents=True, exist_ok=True)
        edition_paths.hooks_config.write_text(
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

        _uninstall_hooks(edition_paths)
        config = json.loads(edition_paths.hooks_config.read_text(encoding="utf-8"))
        assert len(config["hooks"]["post_cascade_response"]) == 1
        assert config["hooks"]["post_cascade_response"][0]["command"] == "other-tool"

    def test_no_error_if_no_hooks_json(self, edition_paths, capsys):
        _uninstall_hooks(edition_paths)
        assert "No hooks.json" in capsys.readouterr().out


class TestUninstallMcpServer:
    def test_removes_server_entry(self, edition_paths):
        edition_paths.mcp_config.parent.mkdir(parents=True, exist_ok=True)
        edition_paths.mcp_config.write_text(
            json.dumps({"mcpServers": {MCP_SERVER_NAME: {"command": "uv"}, "other": {"command": "node"}}}),
            encoding="utf-8",
        )

        _uninstall_mcp_server(edition_paths)
        config = json.loads(edition_paths.mcp_config.read_text(encoding="utf-8"))
        assert MCP_SERVER_NAME not in config["mcpServers"]
        assert "other" in config["mcpServers"]

    def test_no_error_if_no_config(self, edition_paths, capsys):
        _uninstall_mcp_server(edition_paths)
        assert "No mcp_config.json" in capsys.readouterr().out


@pytest.mark.usefixtures("_patch_detect_single")
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

    def test_install_with_edition_flag(self, tmp_path, monkeypatch, capsys):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "SKILL.md").write_text("# skill", encoding="utf-8")
        (project_dir / "learn-review.md").write_text("---\ndescription: test\n---", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "python capture.py")

        run_install(edition="windsurf-next")
        out = capsys.readouterr().out
        assert "Done" in out

    def test_install_no_editions_detected(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr("windsurf_teacher.installer.DB_DIR", tmp_path / "db")
        monkeypatch.setattr("windsurf_teacher.installer.detect_editions", lambda **_kw: [])

        run_install()
        out = capsys.readouterr().out
        assert "Installing" in out
        assert "Done" not in out
        assert not (tmp_path / "db").exists()


class TestRunInstallMultiEdition:
    def test_installs_to_multiple_editions(self, tmp_path, monkeypatch, capsys):
        editions = [
            EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path),
            EditionPaths.for_edition("windsurf-insiders", codeium_base=tmp_path),
        ]
        monkeypatch.setattr("windsurf_teacher.installer.DB_DIR", tmp_path / "db")
        monkeypatch.setattr("windsurf_teacher.installer.detect_editions", lambda **_kw: editions)
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "SKILL.md").write_text("# skill", encoding="utf-8")
        (project_dir / "learn-review.md").write_text("---\ndescription: test\n---", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)
        monkeypatch.setattr("windsurf_teacher.installer._build_hook_command", lambda: "python capture.py")

        run_install(edition="all")
        out = capsys.readouterr().out
        assert "[Windsurf Next (beta)]" in out
        assert "[Windsurf Insiders]" in out
        assert "Done" in out


@pytest.mark.usefixtures("_patch_detect_single")
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


class TestRunUninstallMultiEdition:
    def test_uninstalls_from_multiple_editions(self, tmp_path, monkeypatch, capsys):
        editions = [
            EditionPaths.for_edition("windsurf-next", codeium_base=tmp_path),
            EditionPaths.for_edition("windsurf-insiders", codeium_base=tmp_path),
        ]
        monkeypatch.setattr("windsurf_teacher.installer.DB_DIR", tmp_path / "db")
        monkeypatch.setattr("windsurf_teacher.installer.detect_editions", lambda **_kw: editions)

        run_uninstall(edition="all")
        out = capsys.readouterr().out
        assert "[Windsurf Next (beta)]" in out
        assert "[Windsurf Insiders]" in out
        assert "Done" in out


class TestInstallWorkflow:
    def test_copies_workflow(self, tmp_path, monkeypatch, edition_paths, capsys):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "learn-review.md").write_text("---\ndescription: test\n---", encoding="utf-8")
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_workflow(edition_paths)
        out = capsys.readouterr().out
        assert "Workflow installed" in out
        assert (edition_paths.workflow_dir / "learn-review.md").exists()

    def test_warns_if_workflow_missing(self, tmp_path, monkeypatch, edition_paths, capsys):
        project_dir = tmp_path / "empty-project"
        project_dir.mkdir()
        monkeypatch.setattr("windsurf_teacher.installer.PROJECT_DIR", project_dir)

        _install_workflow(edition_paths)
        out = capsys.readouterr().out
        assert "⚠" in out


class TestUninstallWorkflow:
    def test_removes_workflow(self, edition_paths, capsys):
        edition_paths.workflow_dir.mkdir(parents=True)
        (edition_paths.workflow_dir / "learn-review.md").write_text("test", encoding="utf-8")

        _uninstall_workflow(edition_paths)
        out = capsys.readouterr().out
        assert "Removed workflow" in out
        assert not (edition_paths.workflow_dir / "learn-review.md").exists()

    def test_no_error_if_missing(self, edition_paths, capsys):
        _uninstall_workflow(edition_paths)
        out = capsys.readouterr().out
        assert "not installed" in out
