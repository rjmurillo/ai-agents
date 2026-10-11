"""The seed build step records `complete` only after a clean hook run (issue #6239).

The branching lives in a tested script, not in workflow YAML.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import testmon_seed_build as build


def _runner(returncode: int, calls: list[tuple[list[str], Path]]):
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, Path(str(kwargs["cwd"]))))
        return subprocess.CompletedProcess(command, returncode)

    return run


def test_a_clean_hook_run_records_complete_in_the_step_output(tmp_path: Path) -> None:
    output = tmp_path / "github_output"
    calls: list[tuple[list[str], Path]] = []
    assert build.run_build(tmp_path, output, runner=_runner(0, calls)) == 0
    assert output.read_text(encoding="utf-8") == "complete=true\n"
    assert calls == [([sys.executable, str(build.HOOK_SCRIPT), "pytest"], tmp_path)]


@pytest.mark.parametrize(
    ("returncode", "expected"), [(1, 1), (2, 2), (3, 3), (4, 4), (-9, 1), (-11, 1)]
)
def test_any_other_outcome_fails_the_step_and_records_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], returncode: int, expected: int
) -> None:
    """No failure is hidden: a test failure, budget kill or signal exits nonzero.

    A negative code (a signal) becomes 1, and `complete=true` is never written, so
    the upload step skips and no partial database is uploaded.
    """
    output = tmp_path / "github_output"
    assert build.run_build(tmp_path, output, runner=_runner(returncode, [])) == expected
    assert not output.exists()
    assert "::error::" in capsys.readouterr().out


def test_the_step_output_is_appended_not_replaced(tmp_path: Path) -> None:
    output = tmp_path / "github_output"
    output.write_text("name=testmon-db-x\n", encoding="utf-8")
    build.run_build(tmp_path, output, runner=_runner(0, []))
    assert output.read_text(encoding="utf-8") == "name=testmon-db-x\ncomplete=true\n"


def test_a_clean_run_with_no_output_path_fails_because_it_cannot_be_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean run that cannot record `complete` would silently skip the upload."""
    assert build.run_build(tmp_path, None, runner=_runner(0, [])) == 1
    assert "GITHUB_OUTPUT" in capsys.readouterr().out


def test_the_hook_script_exists() -> None:
    assert build.HOOK_SCRIPT.name == "git_hook_policy.py"
    assert build.HOOK_SCRIPT.is_file()
