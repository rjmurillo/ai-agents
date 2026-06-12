"""Guard: the pinned Python version must be provisionable by uv (issue #2576).

When ``.python-version`` pins a CPython release newer than uv's embedded
interpreter catalog (for example a Renovate bump that outran uv), every
uv-based flow breaks: ``uv run pytest`` fails in fresh containers and the AI
quality gate's pre-executed pytest step errors out with "No interpreter found
for Python <x> in managed installations or search path". The pytest CI jobs
themselves stay green only because ``actions/setup-python`` resolves the minor
series to an older patch, so the breakage is invisible until it reaches a
contributor or the quality gate.

This guard fails fast on such a pin where uv is available (CI, dev machines),
and skips where uv is absent so it never blocks an environment that does not
use uv at all.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_VERSION_FILE = _REPO_ROOT / ".python-version"


def _pinned_version() -> str:
    text = _PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    # .python-version may carry a trailing comment or multiple lines; the pin is
    # the first non-empty token.
    for line in text.splitlines():
        token = line.strip()
        if token and not token.startswith("#"):
            return token
    return ""


def test_python_version_file_exists_and_is_pinned() -> None:
    assert _PYTHON_VERSION_FILE.is_file(), ".python-version must exist"
    version = _pinned_version()
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", version), (
        f"Unexpected .python-version content: {version!r}"
    )


def test_pinned_python_version_is_uv_installable() -> None:
    """The pinned version must appear in uv's provisionable interpreter list."""
    version = _pinned_version()
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not available; cannot verify interpreter provisioning")

    try:
        result = subprocess.run(
            [uv, "python", "list", "--all-versions"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover
        pytest.skip(f"uv python list did not run (offline?): {exc}")

    if result.returncode != 0:  # pragma: no cover
        pytest.skip(f"uv python list failed (rc={result.returncode}); cannot verify")

    listing = result.stdout
    # uv lists interpreters as e.g. "cpython-3.14.6-linux-x86_64-gnu" (installed
    # or "<download available>"). A provisionable pin appears as cpython-<ver>-
    # or cpython-<ver>+ (freethreaded). Match either boundary so 3.14.6 does not
    # spuriously match 3.14.60.
    pattern = re.compile(rf"cpython-{re.escape(version)}[-+]")
    assert pattern.search(listing), (
        f"Pinned Python {version} is not in uv's provisionable list. "
        "uv cannot install it (its catalog is older than this release), so "
        "uv run pytest and the AI quality gate will fail in fresh environments. "
        "Pin .python-version to the newest version uv can provision "
        "(see `uv python list --all-versions`). Refs issue #2576."
    )
