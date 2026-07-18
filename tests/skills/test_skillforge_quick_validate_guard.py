"""Regression tests for the SkillForge quick_validate.py path-traversal guard.

Issue #3224: the CLI guard hardcoded ``~/.claude/skills`` as the only allowed
root, so any skill under the current working directory (a repo checkout, a
Copilot CLI install) was rejected with "Path traversal detected" and could
never be validated. The fix roots the CWE-22 guard at ``os.getcwd()`` to match
the sibling ``validate-skill.py`` and the SKILL.md "current directory" guidance.

These tests exercise the real CLI as the issue's repro does, and run against
both the ``.claude`` copy and the ``src/copilot-cli`` mirror so the two cannot
drift.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPTS = [
    _REPO_ROOT / ".claude" / "skills" / "SkillForge" / "scripts" / "quick_validate.py",
    _REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "SkillForge"
    / "scripts"
    / "quick_validate.py",
]

_TRAVERSAL_MARKER = "Path traversal detected"


def _make_skill(dir_path: Path) -> None:
    """Create a minimal skill directory so the guard has a real target."""
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(
        "---\nname: sample\ndescription: sample skill\n---\n\n# Sample\n",
        encoding="utf-8",
    )


def _run(script: Path, cwd: Path, arg: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), arg],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.parts[-4])
def test_scripts_exist(script: Path) -> None:
    assert script.is_file(), f"missing quick_validate copy: {script}"


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.parts[-4])
def test_skill_under_cwd_passes_traversal_guard(script: Path, tmp_path: Path) -> None:
    # A skill under the current working directory must clear the CWE-22 guard.
    # The final validation verdict is irrelevant here; the guard must not fire.
    _make_skill(tmp_path / "my-skill")
    result = _run(script, cwd=tmp_path, arg="my-skill")
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER not in combined, combined


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.parts[-4])
def test_dotdot_escape_above_cwd_is_rejected(script: Path, tmp_path: Path) -> None:
    # CWE-22 protection is preserved: a path resolving above cwd is rejected.
    outside = tmp_path / "outside-skill"
    _make_skill(outside)
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = _run(script, cwd=workdir, arg="../outside-skill")
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.parts[-4])
def test_absolute_path_outside_cwd_is_rejected(script: Path, tmp_path: Path) -> None:
    # An absolute path outside the working directory is also an escape.
    outside = tmp_path / "elsewhere"
    _make_skill(outside)
    workdir = tmp_path / "work"
    workdir.mkdir()
    result = _run(script, cwd=workdir, arg=str(outside))
    combined = result.stdout + result.stderr
    assert _TRAVERSAL_MARKER in combined, combined
    assert result.returncode == 1
