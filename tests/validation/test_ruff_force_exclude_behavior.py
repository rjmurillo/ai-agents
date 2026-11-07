"""Behavior pins for ruff's force-exclude handling (issue #6506 fail-open-30).

A top-level ``force-exclude = true`` made ``ruff check`` skip files that were
passed by name. The config is now scoped: lint sees named files, and the format
hook passes ``--force-exclude`` itself. These tests run the real ruff from the
dev environment, so a missing ruff fails loudly instead of skipping.

- pos: ``ruff check`` lints a named file in a default-excluded directory
- neg: ``ruff format --check`` without the flag rewrites a format-excluded file
- edge: the same file with ``--force-exclude`` is skipped by the format run
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_FORMAT_EXCLUDED = ".project-toolkit/security/benchmarks/vulnerable_samples/sample.py"


def _ruff(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the dev-environment ruff against the repo config from a scratch directory."""
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, "--config", str(REPO_ROOT / "pyproject.toml")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        check=False,
    )


def test_ruff_is_importable_in_the_dev_environment(tmp_path: Path) -> None:
    result = _ruff(tmp_path, "--version")

    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_check_lints_an_explicit_file_in_a_default_excluded_dir(tmp_path: Path) -> None:
    target = tmp_path / "build" / "unused_import.py"
    target.parent.mkdir()
    target.write_text("import os\n", encoding="utf-8")

    result = _ruff(tmp_path, "check", "--select", "F401", "build/unused_import.py")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "F401" in result.stdout


def test_format_force_exclude_skips_a_format_excluded_file(tmp_path: Path) -> None:
    target = tmp_path / _FORMAT_EXCLUDED
    target.parent.mkdir(parents=True)
    target.write_text("x   =   1\n", encoding="utf-8")

    result = _ruff(tmp_path, "format", "--check", "--force-exclude", _FORMAT_EXCLUDED)

    assert result.returncode == 0, result.stdout + result.stderr


def test_format_without_force_exclude_would_rewrite_the_excluded_file(tmp_path: Path) -> None:
    target = tmp_path / _FORMAT_EXCLUDED
    target.parent.mkdir(parents=True)
    target.write_text("x   =   1\n", encoding="utf-8")

    result = _ruff(tmp_path, "format", "--check", _FORMAT_EXCLUDED)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "would be reformatted" in result.stdout
