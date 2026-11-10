"""Skip a PowerShell test when the launcher exists but cannot start.

A snap-packaged ``pwsh`` can sit on PATH and still refuse to run, printing
``snap-confine is packaged without necessary permissions``. ``shutil.which``
reports it present, so a bare presence check lets the test run and fail on a
machine fault, not on the code under test (issue #7231).

``require_working_pwsh`` runs the launcher once with a trivial command. It
skips only when that probe cannot start. A launcher that starts and then fails
the real assertion still fails the test. On CI the probe never skips a
present launcher, so a broken runner image stays loud.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess

import pytest

# Read at import: tests/conftest.py clears CI before every test body (testing
# rule SHOULD 13), so a read inside the probe would never see it.
_ON_CI = bool(os.environ.get("CI"))

_MARKER = "pwsh-probe-ok"
_PROBE_TIMEOUT_SECONDS = 60


@functools.lru_cache(maxsize=1)
def pwsh_skip_reason() -> str | None:
    """Return why PowerShell tests must skip here, or None when they should run."""
    if shutil.which("pwsh") is None:
        return "pwsh not installed"
    if _ON_CI:
        return None
    try:
        probe = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", f'"{_MARKER}"'],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError as exc:
        return f"pwsh is installed but cannot be launched: {exc} (issue #7231)"
    except subprocess.TimeoutExpired:
        # A hang is not proof the launcher cannot start. Let the test decide.
        return None
    if probe.returncode == 0 and _MARKER in probe.stdout:
        return None
    detail = (probe.stderr or probe.stdout).strip().splitlines()
    first_line = detail[0] if detail else f"exit code {probe.returncode}"
    return f"pwsh is installed but cannot start: {first_line} (issue #7231)"


def require_working_pwsh() -> None:
    """Call at the top of a test that drives ``pwsh``."""
    reason = pwsh_skip_reason()
    if reason is not None:
        pytest.skip(reason)
