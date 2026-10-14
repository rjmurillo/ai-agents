"""Regression coverage for pytest tmp_path retention settings."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

PROBE_MODULE = """
from pathlib import Path


def test_passes(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("pass", encoding="utf-8")


def test_fails(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("fail", encoding="utf-8")
    assert False
"""


MONKEYPATCH_PROBE = """
import os
from pathlib import Path

import pytest


def test_scandir_patch_does_not_reach_the_tmp_path_teardown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "child").mkdir()
    monkeypatch.setattr(os, "scandir", lambda path: (_ for _ in ()).throw(TypeError("patched")))
"""

SIBLING_PROBE = """
from pathlib import Path

import pytest


@pytest.mark.parametrize("case", ["first", "second"])
def test_a_parked_sibling_does_not_block_the_next_owner_of_the_name(
    tmp_path: Path, case: str
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "marker.txt").write_text(case, encoding="utf-8")
"""


def _run_probe(tmp_path: Path, source: str, *extra: str) -> subprocess.CompletedProcess[str]:
    probe = tmp_path / "test_probe.py"
    probe.write_text(source, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(probe),
            "-c",
            str(PYPROJECT),
            "--rootdir",
            str(tmp_path),
            f"--basetemp={tmp_path / 'base'}",
            "-p",
            "tests.conftest",
            "-p",
            "no:cacheprovider",
            "-q",
            "--disable-warnings",
            *extra,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _ini_options() -> dict[str, object]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]


def test_retention_count_keeps_one_basetemp_tree() -> None:
    assert _ini_options()["tmp_path_retention_count"] == 1


def test_retention_policy_keeps_only_failed_test_dirs() -> None:
    assert _ini_options()["tmp_path_retention_policy"] == "failed"


def test_retention_policy_removes_passed_dirs_and_keeps_failed_dirs(tmp_path: Path) -> None:
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE_MODULE, encoding="utf-8")
    basetemp = tmp_path / "base"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(probe),
            "-c",
            str(PYPROJECT),
            "--rootdir",
            str(tmp_path),
            f"--basetemp={basetemp}",
            "-p",
            "no:cacheprovider",
            "-q",
            "--disable-warnings",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    kept = sorted(path.name for path in basetemp.iterdir() if not path.is_symlink())
    assert kept == ["test_fails0"]
    assert not (basetemp / "test_passes0").exists()


def test_a_patch_on_os_is_undone_before_tmp_path_is_removed(tmp_path: Path) -> None:
    result = _run_probe(tmp_path, MONKEYPATCH_PROBE)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert "error" not in result.stdout.lower()


def test_a_sibling_parked_beside_a_removed_tmp_path_does_not_collide(tmp_path: Path) -> None:
    result = _run_probe(tmp_path, SIBLING_PROBE)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
