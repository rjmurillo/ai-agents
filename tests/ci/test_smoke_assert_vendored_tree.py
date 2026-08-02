"""Tests for scripts/ci/smoke_assert_vendored_tree.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.smoke_assert_vendored_tree import main, run


class TestRun:
    def test_missing_demo_env_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DEMO", None)
            assert run() == 1

    def test_all_paths_present_returns_0(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        claude = demo / ".claude"
        (claude / "agents").mkdir(parents=True)
        (claude / "commands").mkdir()
        (claude / "skills").mkdir()
        (demo / "CLAUDE.md").write_text("x")
        (demo / "AGENTS.md").write_text("x")
        (claude / ".ai-agents-version.json").write_text("{}")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0

    def test_missing_agents_dir_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        claude = demo / ".claude"
        claude.mkdir()
        # agents dir intentionally not created
        (claude / "commands").mkdir()
        (claude / "skills").mkdir()
        (demo / "CLAUDE.md").write_text("x")
        (demo / "AGENTS.md").write_text("x")
        (claude / ".ai-agents-version.json").write_text("{}")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_missing_leaf_file_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        claude = demo / ".claude"
        (claude / "agents").mkdir(parents=True)
        (claude / "commands").mkdir()
        (claude / "skills").mkdir()
        # CLAUDE.md intentionally absent
        (demo / "AGENTS.md").write_text("x")
        (claude / ".ai-agents-version.json").write_text("{}")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_error_message_on_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        (demo / ".claude").mkdir()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            run()
        out = capsys.readouterr().out
        assert "::error::" in out

    def test_success_message_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        demo.mkdir()
        claude = demo / ".claude"
        (claude / "agents").mkdir(parents=True)
        (claude / "commands").mkdir()
        (claude / "skills").mkdir()
        (demo / "CLAUDE.md").write_text("x")
        (demo / "AGENTS.md").write_text("x")
        (claude / ".ai-agents-version.json").write_text("{}")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            run()
        out = capsys.readouterr().out
        assert "Vendored tree OK" in out


class TestMain:
    def test_main_delegates_to_run(self) -> None:
        with patch("scripts.ci.smoke_assert_vendored_tree.run", return_value=9):
            assert main() == 9
