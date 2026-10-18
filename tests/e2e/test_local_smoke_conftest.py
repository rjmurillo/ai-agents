"""Tests that the e2e conftest arms the local Copilot guard end to end."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_smoke_guard as guard
from local_smoke_command import program_names


def _copy_suite(tmp_path: Path) -> None:
    """Copy the conftest and the guard modules into a throwaway suite."""
    e2e_dir = Path(__file__).resolve().parent
    for name in ("conftest.py", "local_smoke_guard.py", "local_smoke_command.py"):
        (tmp_path / name).write_text((e2e_dir / name).read_text(encoding="utf-8"), encoding="utf-8")


def _run_unmarked_copilot_test(
    tmp_path: Path, *, armed: bool, at_import: bool = False, by_name: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a throwaway suite that calls a fake ``copilot`` with no marker.

    With ``at_import`` the call runs at module import, during collection. With ``by_name``
    the call is ``bash -c 'builtin exec copilot'``, a form the command parser does not read.
    """
    _copy_suite(tmp_path)
    fake = tmp_path / "bin" / "copilot"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    fake.chmod(0o755)
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    argv = ["bash", "-c", "builtin exec copilot"] if by_name else [str(fake)]
    call = f"subprocess.run({argv!r}, check=True)\n"
    body = call if at_import else f"def test_unmarked_copilot_call():\n    {call}"
    (tmp_path / "test_unmarked.py").write_text(
        "import subprocess\n\n" + body + "\n\ndef test_placeholder():\n    pass\n",
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k != guard.LOCAL_SMOKE_ENV}
    if armed:
        env[guard.LOCAL_SMOKE_ENV] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", "pytest.ini", "."],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_conftest_fails_an_unmarked_copilot_call_under_the_gate_flag(tmp_path: Path) -> None:
    result = _run_unmarked_copilot_test(tmp_path, armed=True)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "must not call Copilot" in result.stdout


def test_conftest_refuses_a_copilot_call_during_collection(tmp_path: Path) -> None:
    """Edge: the guard is armed before test modules import, not only per test."""
    result = _run_unmarked_copilot_test(tmp_path, armed=True, at_import=True)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "must not call Copilot" in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="the shim is a shell script")
def test_conftest_shim_fails_a_launch_by_name_the_parser_misses(tmp_path: Path) -> None:
    """The PATH shim catches a launch by name that the argument guard cannot read."""
    assert "copilot" not in program_names(["bash", "-c", "builtin exec copilot"])

    result = _run_unmarked_copilot_test(tmp_path, armed=True, by_name=True)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CalledProcessError" in result.stdout
    assert "must not call Copilot" in result.stdout + result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="the fake copilot is a shebang script")
def test_conftest_leaves_copilot_alone_without_the_gate_flag(tmp_path: Path) -> None:
    """Negative control: CI's copilot leg never sets the flag, so calls proceed."""
    result = _run_unmarked_copilot_test(tmp_path, armed=False)

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="the shim is a shell script")
def test_a_test_that_uninstalls_the_guard_leaves_the_session_guard_armed(tmp_path: Path) -> None:
    """A test using ``isolated_guard`` must not strip the guard from tests that run after it."""
    _copy_suite(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_a_strips.py").write_text(
        "import local_smoke_guard as guard\n\n"
        "def test_strips(isolated_guard):\n"
        "    guard.uninstall()\n"
        "    guard.remove_path_shim()\n",
        encoding="utf-8",
    )
    (tmp_path / "test_b_checks.py").write_text(
        "import os, shutil, subprocess\n"
        "import local_smoke_guard as guard\n\n"
        "def test_guard_still_armed():\n"
        "    assert subprocess.Popen is guard.GuardedPopen\n"
        "    assert shutil.which('copilot') is not None\n"
        "    assert os.path.dirname(shutil.which('copilot')).startswith(guard._shim_dir.name)\n",
        encoding="utf-8",
    )
    env = {**os.environ, guard.LOCAL_SMOKE_ENV: "1"}

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", "pytest.ini", "."],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
