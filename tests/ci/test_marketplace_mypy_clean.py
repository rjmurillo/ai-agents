"""Regression guard for mypy clean state on marketplace tests (issue #4199).

PR #4093 merged a mypy error on ``tests/test_marketplace_two_plugin.py:179``
(``Value of type Collection[str] is not indexable [index]``).  The error was
invisible to the local hook because ``git_hook_policy.py mypy`` is scoped to
pushed files; a file nobody touched carried the error indefinitely.

This test verifies the file stays mypy-clean, runs in CI via pytest.yml, and
cannot false-green on an empty file set the way the hook-based check can.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _REPO_ROOT / "tests" / "test_marketplace_two_plugin.py"


def test_marketplace_test_passes_mypy() -> None:
    """tests/test_marketplace_two_plugin.py must pass mypy with zero errors."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            str(_TARGET),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    errors = [
        line for line in result.stdout.splitlines()
        if "error:" in line and str(_TARGET.name) in line
    ]
    assert result.returncode == 0 and not errors, (
        f"mypy found errors in {_TARGET.relative_to(_REPO_ROOT)}:\n"
        + "\n".join(errors or result.stdout.splitlines())
    )

