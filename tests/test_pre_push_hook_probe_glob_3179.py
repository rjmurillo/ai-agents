#!/usr/bin/env python3
"""Regression coverage for Issue #3179: pre-push glob gap on the shared probe.

PR #3167 (fixes #3148) extracted the fired-hook probe into
``tests/e2e/copilot_hook_probe.py``, imported by both ``test_cli_hook_e2e.py``
and ``test_plugin_load_smoke.py``. The ``CHANGED_HOOKS`` and
``CHANGED_PLUGIN_LOAD`` trigger globs in ``scripts/hooks/pre-push`` did not match
the helper, so editing it alone would ship without either smoke firing, a
silent gap on a customer-facing push gate.

These tests extract each glob's extended-regex from the hook and assert the
helper path matches both, with negative and preservation controls so the fix
cannot silently regress or over-broaden.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_PUSH = REPO_ROOT / "scripts" / "hooks" / "pre-push"
HELPER = "tests/e2e/copilot_hook_probe.py"


def _extract_glob(var_name: str) -> str:
    """Return the extended-regex a pre-push glob assignment feeds to grep -E.

    Parses the line ``VAR=$(echo "$CHANGED_FILES" | grep -E 'ERE' || true)`` and
    returns the single-quoted ERE. The ERE is anchored, so it is usable directly
    with ``re.match`` (ERE alternation, groups, and ``\\.`` are all valid
    Python regex).
    """
    text = PRE_PUSH.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(var_name)}=.*grep -E '([^']+)'", re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        raise AssertionError(f"{var_name} grep -E assignment not found in pre-push")
    return match.group(1)


def test_helper_matches_changed_hooks_glob() -> None:
    ere = _extract_glob("CHANGED_HOOKS")
    assert re.match(ere, HELPER), (
        f"{HELPER} must match CHANGED_HOOKS so editing the shared probe "
        f"retriggers the CLI hook e2e (#3179). ERE: {ere!r}"
    )


def test_helper_matches_changed_plugin_load_glob() -> None:
    ere = _extract_glob("CHANGED_PLUGIN_LOAD")
    assert re.match(ere, HELPER), (
        f"{HELPER} must match CHANGED_PLUGIN_LOAD so editing the shared probe "
        f"retriggers the plugin-load smoke (#3179). ERE: {ere!r}"
    )


def test_unrelated_path_does_not_match_either_glob() -> None:
    # Negative control: a plain source file outside the trigger sets must not
    # match, proving the globs stayed narrow after the fix.
    unrelated = "scripts/detect_scope_explosion.py"
    assert not re.match(_extract_glob("CHANGED_HOOKS"), unrelated)
    assert not re.match(_extract_glob("CHANGED_PLUGIN_LOAD"), unrelated)


def test_existing_smoke_triggers_are_preserved() -> None:
    # Preservation control: the fix must not drop the smokes' own paths.
    hooks_ere = _extract_glob("CHANGED_HOOKS")
    plugin_ere = _extract_glob("CHANGED_PLUGIN_LOAD")
    assert re.match(hooks_ere, "tests/e2e/test_cli_hook_e2e.py")
    assert re.match(plugin_ere, "tests/e2e/test_plugin_load_smoke.py")
