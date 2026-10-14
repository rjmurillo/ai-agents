"""The process-group kill helpers type-check for Windows too (issue #6412).

``os.killpg``, ``os.getpgid`` and ``signal.SIGKILL`` do not exist on Windows.
A ``hasattr`` guard keeps them from running there, but mypy cannot read that
guard, so the pre-push type check on a Windows runner failed on every call.
mypy reads a ``sys.platform`` check, so each helper that touches those names
must sit behind one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MODULES = (
    "scripts/validation/subprocess_runner.py",
    "scripts/validation/run_workflow_local_test.py",
)


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
@pytest.mark.parametrize("module", _MODULES)
def test_kill_helpers_type_check_on_every_platform(module: str, platform: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--platform",
            platform,
            "--no-incremental",
            module,
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
