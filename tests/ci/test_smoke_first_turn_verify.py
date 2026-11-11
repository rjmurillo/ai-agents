"""Tests for scripts/ci/smoke_first_turn_verify.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.smoke_first_turn_verify import main, run


class TestRun:
    def test_missing_demo_env_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DEMO", None)
            assert run() == 1

    def test_no_banned_paths_returns_0(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        (demo / ".claude").mkdir()
        # No banned paths created

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0

    def test_hooks_dir_present_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = demo / ".claude"
        (claude / "hooks").mkdir(parents=True)

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_lib_dir_present_returns_0(self, tmp_path: Path) -> None:
        # Skill scripts import from <root>/lib (ADR-047), so it must ship.
        demo = tmp_path / "demo"
        claude = demo / ".claude"
        (claude / "lib").mkdir(parents=True)
        (claude / "lib" / "paths.py").write_text("x = 1\n")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0

    @pytest.mark.parametrize("name", ["CLAUDE.md", "AGENTS.md"])
    def test_maintainer_instructions_present_returns_1(
        self, tmp_path: Path, name: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        claude = demo / ".claude"
        claude.mkdir(parents=True)
        (claude / name).write_text("maintainer")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1
        assert f"excluded path vendored: {claude / name}" in capsys.readouterr().out

    def test_skill_level_claude_md_is_allowed(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        skill = demo / ".claude" / "skills" / "memory"
        skill.mkdir(parents=True)
        (skill / "CLAUDE.md").write_text("skill-level")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0

    def test_project_root_claude_md_is_allowed(self, tmp_path: Path) -> None:
        # The CLI merges its block into <project>/CLAUDE.md; only .claude/CLAUDE.md is banned.
        demo = tmp_path / "demo"
        (demo / ".claude").mkdir(parents=True)
        (demo / "CLAUDE.md").write_text("consumer")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0

    def test_settings_json_present_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = demo / ".claude"
        claude.mkdir(parents=True)
        (claude / "settings.json").write_text("{}")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_skills_github_present_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = demo / ".claude"
        (claude / "skills" / "github").mkdir(parents=True)

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_error_annotation_on_banned_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        (demo / ".claude" / "hooks").mkdir(parents=True)

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            run()
        assert "::error::" in capsys.readouterr().out

    def test_success_message_when_clean(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            run()
        assert "First-turn lint OK" in capsys.readouterr().out


class TestMain:
    def test_main_delegates_to_run(self) -> None:
        with patch("scripts.ci.smoke_first_turn_verify.run", return_value=4):
            assert main() == 4
