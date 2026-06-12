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
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_VERSION_FILE = _REPO_ROOT / ".python-version"


def _pinned_version() -> str:
    text = _PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    # .python-version may carry a trailing comment or multiple lines; the pin is
    # the first non-empty token.
    for line in text.splitlines():
        token = line.split("#", 1)[0].strip().split(maxsplit=1)[0]
        if token and not token.startswith("#"):
            return token
    return ""


def _uv_cpython_pattern(version: str) -> re.Pattern[str]:
    return re.compile(rf"cpython-{re.escape(version)}(?!\d)")


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
            encoding="utf-8",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover
        pytest.skip(f"uv python list did not run (offline?): {exc}")

    if result.returncode != 0:  # pragma: no cover
        pytest.skip(f"uv python list failed (rc={result.returncode}); cannot verify")

    listing = result.stdout
    # uv lists interpreters as e.g. "cpython-3.14.6-linux-x86_64-gnu"
    # (installed or "<download available>"). A minor pin such as "3.14" should
    # match any listed 3.14.x patch, while a patch pin such as "3.14.6" must not
    # match 3.14.60.
    pattern = _uv_cpython_pattern(version)
    assert pattern.search(listing), (
        f"Pinned Python {version} is not in uv's provisionable list. "
        "uv cannot install it (its catalog is older than this release), so "
        "uv run pytest and the AI quality gate will fail in fresh environments. "
        "Pin .python-version to the newest version uv can provision "
        "(see `uv python list --all-versions`). Refs issue #2576."
    )


def test_pinned_version_strips_inline_comment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    version_file = tmp_path / ".python-version"
    version_file.write_text("3.14.6 # renovate managed\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "_PYTHON_VERSION_FILE", version_file)

    assert _pinned_version() == "3.14.6"


def test_uv_pattern_allows_minor_pin_to_match_patch() -> None:
    pattern = _uv_cpython_pattern("3.14")

    assert pattern.search("cpython-3.14.6-linux-x86_64-gnu")
    assert not pattern.search("cpython-3.140.1-linux-x86_64-gnu")


def test_uv_pattern_patch_pin_does_not_match_longer_patch() -> None:
    pattern = _uv_cpython_pattern("3.14.6")

    assert pattern.search("cpython-3.14.6-linux-x86_64-gnu")
    assert not pattern.search("cpython-3.14.60-linux-x86_64-gnu")
