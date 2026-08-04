"""Tests for write_copilot_synthesis_summary.py (ADR-006 burn-down, issue #2967)."""

from __future__ import annotations

import subprocess
from pathlib import Path

_SCRIPT = Path("scripts/ci/write_copilot_synthesis_summary.py")


def _run(env: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    import os

    full_env = {**os.environ, **env}
    # GitHub Actions always sets GITHUB_STEP_SUMMARY. Inheriting it makes the
    # script write to that file instead of stdout, so the stdout assertions
    # below pass locally and fail in CI. Drop the inherited value unless the
    # caller asked for a summary file explicitly.
    if "GITHUB_STEP_SUMMARY" not in env:
        full_env.pop("GITHUB_STEP_SUMMARY", None)
    # A CI runner exports GITHUB_STEP_SUMMARY. Inheriting it sends the script's
    # output to the real step summary instead of stdout, so the stdout
    # assertions below read an empty string and fail only under CI.
    if "GITHUB_STEP_SUMMARY" not in env:
        full_env.pop("GITHUB_STEP_SUMMARY", None)
    return subprocess.run(
        ["uv", "run", "--frozen", "python", str(_SCRIPT)],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=Path(__file__).parents[2],
    )


class TestHappyPath:
    def test_writes_to_stdout_when_no_summary_file(self) -> None:
        result = _run({"ISSUE_NUMBER": "42"}, Path())
        assert result.returncode == 0
        assert "Copilot Context Synthesis Complete" in result.stdout
        assert "#42" in result.stdout

    def test_writes_expected_sections(self) -> None:
        result = _run({"ISSUE_NUMBER": "99"}, Path())
        assert result.returncode == 0
        assert "### Actions Taken" in result.stdout
        assert "#99" in result.stdout
        assert "Copilot will now create a PR" in result.stdout

    def test_writes_to_summary_file(self, tmp_path: Path) -> None:
        summary_file = tmp_path / "step_summary.md"
        result = _run(
            {"ISSUE_NUMBER": "7", "GITHUB_STEP_SUMMARY": str(summary_file)},
            tmp_path,
        )
        assert result.returncode == 0
        content = summary_file.read_text()
        assert "#7" in content
        assert "Copilot Context Synthesis Complete" in content


class TestNegativeControl:
    def test_exits_2_when_issue_number_missing(self) -> None:
        result = _run({"ISSUE_NUMBER": ""}, Path())
        assert result.returncode == 2
        assert "ISSUE_NUMBER" in result.stderr

    def test_no_output_on_error(self) -> None:
        result = _run({"ISSUE_NUMBER": ""}, Path())
        assert result.stdout == ""


class TestEdgeCases:
    def test_appends_to_existing_summary_file(self, tmp_path: Path) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.write_text("# Existing content\n")
        _run({"ISSUE_NUMBER": "5", "GITHUB_STEP_SUMMARY": str(summary_file)}, tmp_path)
        content = summary_file.read_text()
        assert "# Existing content" in content
        assert "#5" in content

    def test_issue_number_appears_once_in_output(self) -> None:
        result = _run({"ISSUE_NUMBER": "123"}, Path())
        assert result.stdout.count("#123") == 1
