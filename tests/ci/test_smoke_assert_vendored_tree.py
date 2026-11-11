"""Tests for scripts/ci/smoke_assert_vendored_tree.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.smoke_assert_vendored_tree import PROBE_SCRIPTS, main, run

OK_SCRIPT = "import sys\nsys.exit(0)\n"


def _make_tree(demo: Path, *, script_body: str = OK_SCRIPT) -> Path:
    """Build a vendored tree that satisfies every expected path."""
    claude = demo / ".claude"
    (claude / "agents").mkdir(parents=True)
    (claude / "skills").mkdir()
    (claude / "lib").mkdir()
    (claude / "lib" / "paths.py").write_text("x = 1\n")
    for relative in PROBE_SCRIPTS:
        script = claude / relative
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(script_body)
    (demo / "CLAUDE.md").write_text("x")
    (demo / "AGENTS.md").write_text("x")
    (claude / ".ai-agents-version.json").write_text("{}")
    return claude


class TestRun:
    def test_missing_demo_env_returns_1(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DEMO", None)
            assert run() == 1

    def test_all_paths_present_returns_0(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        _make_tree(demo)

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0

    def test_missing_agents_dir_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = _make_tree(demo)
        (claude / "agents").rmdir()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_missing_leaf_file_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        _make_tree(demo)
        (demo / "CLAUDE.md").unlink()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_missing_lib_dir_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = _make_tree(demo)
        (claude / "lib" / "paths.py").unlink()
        (claude / "lib").rmdir()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_missing_lib_paths_module_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = _make_tree(demo)
        (claude / "lib" / "paths.py").unlink()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_probe_script_failing_help_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        claude = _make_tree(demo)
        broken = claude / PROBE_SCRIPTS[0]
        broken.write_text("raise RuntimeError('lib directory not found')\n")

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1
        out = capsys.readouterr().out
        assert "::error::vendored script failed --help" in out
        assert "lib directory not found" in out

    def test_probe_script_missing_returns_1(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = _make_tree(demo)
        (claude / PROBE_SCRIPTS[1]).unlink()

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 1

    def test_probe_runs_every_listed_script_with_help(self, tmp_path: Path) -> None:
        demo = tmp_path / "demo"
        claude = _make_tree(demo)
        marker_dir = tmp_path / "marks"
        marker_dir.mkdir()
        body = (
            "import sys, pathlib\n"
            "pathlib.Path(sys.argv[0]).with_suffix('.mark').write_text(' '.join(sys.argv[1:]))\n"
        )
        for relative in PROBE_SCRIPTS:
            (claude / relative).write_text(body)

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            assert run() == 0
        for relative in PROBE_SCRIPTS:
            assert (claude / relative).with_suffix(".mark").read_text() == "--help"

    def test_probe_drops_plugin_root_env_so_it_cannot_mask_a_missing_lib(
        self, tmp_path: Path
    ) -> None:
        demo = tmp_path / "demo"
        _make_tree(
            demo,
            script_body=(
                "import os, sys\n"
                "names = ('CLAUDE_PLUGIN_ROOT', 'COPILOT_PLUGIN_ROOT')\n"
                "sys.exit(1 if any(k in os.environ for k in names) else 0)\n"
            ),
        )

        env = {
            "DEMO": str(demo),
            "CLAUDE_PLUGIN_ROOT": "/elsewhere",
            "COPILOT_PLUGIN_ROOT": "/else",
        }
        with patch.dict(os.environ, env):
            assert run() == 0

    def test_probe_timeout_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        demo = tmp_path / "demo"
        _make_tree(demo)

        def boom(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired(cmd="x", timeout=1)

        with (
            patch.dict(os.environ, {"DEMO": str(demo)}),
            patch("scripts.ci.smoke_assert_vendored_tree.subprocess.run", side_effect=boom),
        ):
            assert run() == 1
        assert "timed out" in capsys.readouterr().out

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
        _make_tree(demo)

        with patch.dict(os.environ, {"DEMO": str(demo)}):
            run()
        out = capsys.readouterr().out
        assert "Vendored tree OK" in out
        assert f"{len(PROBE_SCRIPTS)} scripts ran --help" in out


class TestMain:
    def test_main_delegates_to_run(self) -> None:
        with patch("scripts.ci.smoke_assert_vendored_tree.run", return_value=9):
            assert main() == 9
