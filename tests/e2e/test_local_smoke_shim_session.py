"""The PATH shim and the isolated_guard fixture through the e2e conftest (issue #6506)."""

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

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the shim is a shell script")


def _run_suite(tmp_path: Path, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a throwaway suite under the gate flag, with the real conftest and guard modules."""
    e2e_dir = Path(__file__).resolve().parent
    names = ["conftest.py", *(f.name for f in e2e_dir.glob("local_smoke_*.py"))]
    for name in names:
        (tmp_path / name).write_text((e2e_dir / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", "pytest.ini", "."],
        cwd=tmp_path,
        env={**os.environ, guard.LOCAL_SMOKE_ENV: "1"},
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def test_conftest_shim_fails_a_launch_by_name_the_parser_misses(tmp_path: Path) -> None:
    """The PATH shim catches a launch by name that the argument guard cannot read."""
    argv = ["bash", "-c", "builtin exec copilot"]
    assert "copilot" not in program_names(argv)

    result = _run_suite(
        tmp_path,
        {
            "test_unmarked.py": "import subprocess\n\n"
            f"def test_unmarked_copilot_call():\n    subprocess.run({argv!r}, check=True)\n"
        },
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CalledProcessError" in result.stdout
    assert "must not call Copilot" in result.stdout + result.stderr


def test_a_test_that_uninstalls_the_guard_leaves_the_session_guard_armed(tmp_path: Path) -> None:
    """A test using ``isolated_guard`` must not strip the guard from tests that run after it."""
    result = _run_suite(
        tmp_path,
        {
            "test_a_strips.py": "import local_smoke_guard as guard\n"
            "from local_smoke_fixtures import isolated_guard\n"
            "import local_smoke_shim as shim\n\n"
            "def test_strips(isolated_guard):\n"
            "    guard.uninstall()\n"
            "    shim.remove_path_shim()\n",
            "test_b_checks.py": "import os, shutil, subprocess\n"
            "import local_smoke_guard as guard\n"
            "import local_smoke_shim as shim\n\n"
            "def test_guard_still_armed():\n"
            "    assert subprocess.Popen is guard.GuardedPopen\n"
            "    found = shutil.which('copilot')\n"
            "    assert found is not None\n"
            "    assert os.path.dirname(found) == shim._shim_dir.name\n",
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
