#!/usr/bin/env python3
"""Regression coverage for Issue #2327: a pre-push run stays tree-neutral.

Two dirtying sources are guarded here at the script-content level:

1. ``uv run`` must pass ``--frozen`` so a pre-push run cannot re-resolve and
   rewrite ``uv.lock``.
2. The pre-push hook drops an auto-retro suppression sentinel under the
   gitignored ``.agents/.hook-state/`` and removes it on exit, so a session
   ending mid-run does not leave an untracked auto-retro file or a
   ``docs/retros/INDEX.md`` edit behind.

The runtime suppression behavior of the Stop hook itself is covered in
``tests/test_auto_retrospective.py`` (TestAutoRetroSuppressionSentinel). Here we
pin the producer side: the bash hook writes the exact sentinel the Stop hook
reads, and pins the lockfile.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / ".githooks" / "pre-push"

# Import the Stop hook to read the canonical sentinel constant so the two
# files cannot drift (the bash hook writes what the Python hook reads).
sys.path.insert(0, str(REPO_ROOT / ".claude" / "hooks" / "Stop"))
import invoke_auto_retrospective  # noqa: E402


def _pre_push_text() -> str:
    return PRE_PUSH.read_text(encoding="utf-8")


def test_uv_run_is_frozen() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: the uv invocation pins the lockfile; bare ``uv run python`` is gone.
    assert "uv run --frozen python" in text
    assert "PYTHON_CMD=(uv run --frozen python)" in text


def test_no_unfrozen_uv_run_python_remains() -> None:
    # Arrange
    text = _pre_push_text()

    # Assert: no bare ``uv run python`` (without --frozen) survives. Allow the
    # token to appear only as part of ``uv run --frozen python``.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "uv run python" in stripped:
            raise AssertionError(
                f"unfrozen 'uv run python' found in pre-push: {stripped!r}"
            )


def test_uv_frozen_failure_blocks_system_python_fallback() -> None:
    # Arrange
    text = _pre_push_text()
    set_python_body = text[
        text.index("set_python_cmd() {") : text.index(
            "# Determine changed files", text.index("set_python_cmd() {")
        )
    ]

    # Assert: stale lock or pyproject errors fail the push instead of silently
    # running later validators under a different system Python.
    assert "uv run --frozen python -c 'import sys'" in set_python_body
    assert "uv is required for this checkout" in set_python_body
    assert "Refusing system Python fallback in a uv-managed checkout" in set_python_body
    assert set_python_body.index("return 1") < set_python_body.index("# Try python3")


def test_sentinel_written_and_cleaned() -> None:
    # Arrange
    text = _pre_push_text()
    sentinel_name = invoke_auto_retrospective.AUTO_RETRO_SUPPRESS_SENTINEL

    # Assert: the hook references the sentinel under .agents/.hook-state/ and
    # removes it in cleanup().
    assert f".agents/.hook-state/{sentinel_name}" in text
    assert 'rm -f "$AUTO_RETRO_SUPPRESS_SENTINEL"' in text


def test_sentinel_name_matches_stop_hook_contract() -> None:
    # The bash hook writes the file the Stop hook scans for. The Stop hook
    # owns the name (constant AUTO_RETRO_SUPPRESS_SENTINEL); the bash hook must
    # use that exact basename or suppression silently breaks.
    text = _pre_push_text()
    assert invoke_auto_retrospective.AUTO_RETRO_SUPPRESS_SENTINEL == (
        "auto-retrospective.suppress"
    )
    assert "auto-retrospective.suppress" in text


def test_hook_state_dir_is_gitignored() -> None:
    # The sentinel lives under a gitignored directory so it never dirties the
    # tree. Guard that .gitignore still covers it (the whole point of #2327).
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".agents/.hook-state/" in gitignore


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
