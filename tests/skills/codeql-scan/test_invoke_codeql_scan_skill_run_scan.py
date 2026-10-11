#!/usr/bin/env python3
"""Tests for run_scan in invoke_codeql_scan_skill: delegate discovery and exit codes."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/codeql-scan/scripts/invoke_codeql_scan_skill.py")
run_scan = mod.run_scan


def _touch(root: Path, *relative_paths: str) -> None:
    """Create each file under root, with its parent directories."""
    for relative in relative_paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def _run_scan_in(root: Path | None, operation: str = "full", run_effect: object = None) -> int:
    """Call run_scan with get_repo_root pointed at root and subprocess.run stubbed."""
    repo_root = None if root is None else str(root)
    if isinstance(run_effect, type) and issubclass(run_effect, BaseException):
        run_patch = patch("subprocess.run", side_effect=run_effect)
    else:
        run_patch = patch("subprocess.run", return_value=MagicMock(returncode=0))
    with patch.object(mod, "get_repo_root", return_value=repo_root), run_patch:
        return int(run_scan(operation=operation))


_CLI = ".codeql/cli/codeql"
_SCAN_SCRIPT = ".codeql/scripts/invoke_codeql_scan.py"
_CONFIG_SCRIPT = ".codeql/scripts/test_codeql_config.py"


class TestRunScan:
    """Tests for run_scan function."""

    def test_returns_3_when_not_in_repo(self) -> None:
        assert _run_scan_in(None) == 3

    def test_validate_returns_3_when_config_missing(self, tmp_path: Path) -> None:
        assert _run_scan_in(tmp_path, operation="validate") == 3

    def test_returns_3_when_codeql_cli_missing(self, tmp_path: Path) -> None:
        assert _run_scan_in(tmp_path) == 3

    def test_returns_3_when_scan_script_missing(self, tmp_path: Path) -> None:
        _touch(tmp_path, _CLI)
        assert _run_scan_in(tmp_path) == 3

    def test_validate_returns_0_when_delegate_succeeds(self, tmp_path: Path) -> None:
        _touch(tmp_path, _CONFIG_SCRIPT)
        assert _run_scan_in(tmp_path, operation="validate") == 0

    def test_validate_returns_3_when_delegate_cannot_launch(self, tmp_path: Path) -> None:
        """A launch failure is exit 3, not a false success (Issue #4921).

        The delegate exists, so the run reaches subprocess. Named for pwsh
        until #4921; the wrapper now launches sys.executable.
        """
        _touch(tmp_path, _CONFIG_SCRIPT)
        assert _run_scan_in(tmp_path, operation="validate", run_effect=FileNotFoundError) == 3

    def test_full_returns_0_with_cli_and_scan_script(self, tmp_path: Path) -> None:
        _touch(tmp_path, _CLI, _SCAN_SCRIPT)
        assert _run_scan_in(tmp_path) == 0
