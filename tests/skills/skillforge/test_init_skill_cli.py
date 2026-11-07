"""CLI contract of skillforge init_skill.py: --dry-run writes nothing."""

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
    / "init_skill.py"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_dry_run_reports_target_and_creates_nothing(tmp_path: Path) -> None:
    result = run("my-skill", "--path", str(tmp_path), "--dry-run")

    assert result.returncode == 0
    assert "Dry run: would create" in result.stdout
    assert not (tmp_path / "my-skill").exists()


def test_real_run_creates_the_scaffold(tmp_path: Path) -> None:
    result = run("my-skill", "--path", str(tmp_path))

    assert result.returncode == 0
    assert (tmp_path / "my-skill" / "SKILL.md").is_file()


def test_dry_run_still_refuses_an_existing_directory(tmp_path: Path) -> None:
    (tmp_path / "my-skill").mkdir()

    result = run("my-skill", "--path", str(tmp_path), "--dry-run")

    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_dry_run_still_rejects_a_bad_name(tmp_path: Path) -> None:
    result = run("Bad_Name", "--path", str(tmp_path), "--dry-run")

    assert result.returncode == 2
    assert result.stdout == ""


def test_dry_run_still_rejects_a_missing_parent(tmp_path: Path) -> None:
    result = run("my-skill", "--path", str(tmp_path / "absent"), "--dry-run")

    assert result.returncode == 2
