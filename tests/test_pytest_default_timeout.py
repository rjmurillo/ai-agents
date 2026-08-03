"""Regression coverage for the default pytest-timeout guard (issue #4184)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_pytest_addopts_declares_default_per_test_timeout() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    addopts = data["tool"]["pytest"]["ini_options"]["addopts"].split()

    assert "--timeout=120" in addopts


def test_pytest_timeout_terminates_hanging_test_module(tmp_path: Path) -> None:
    hanging_test = tmp_path / "test_hangs.py"
    hanging_test.write_text(
        "import time\n\n"
        "def test_hangs_longer_than_timeout():\n"
        "    time.sleep(10)\n",
        encoding="utf-8",
    )

    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(hanging_test),
            "--rootdir",
            str(REPO_ROOT),
            "--timeout=1",
            "-q",
            "--tb=short",
            "--disable-warnings",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    elapsed = time.monotonic() - started
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert elapsed < 8
    assert "Timeout" in output
