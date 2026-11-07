"""CLI contract of skillforge package_skill.py: argparse help and stderr failures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "skillforge"
    / "scripts"
    / "package_skill.py"
)


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        check=False,
    )


def test_help_exits_zero_and_lists_examples_and_exit_codes() -> None:
    result = run("--help")

    assert result.returncode == 0
    assert "examples:" in result.stdout
    assert "exit codes:" in result.stdout
    assert "packaging skill" not in result.stdout.lower()


def test_missing_argument_exits_two_with_usage_on_stderr() -> None:
    result = run()

    assert result.returncode == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr


def test_unknown_flag_exits_two() -> None:
    assert run("--bogus").returncode == 2


def test_failed_package_reports_the_error_on_stderr(tmp_path: Path) -> None:
    result = run(str(tmp_path / "absent-skill"), cwd=tmp_path)

    assert result.returncode == 1
    assert "Please fix the errors" in result.stderr
    assert "Please fix the errors" not in result.stdout
