#!/usr/bin/env python3
"""Review-marker and command-bundle coverage gates for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Groups the two
advisory-by-default gates that report on the SHA-bound ``/review`` marker and
on each lifecycle command invoking its bundled skills.

Behavior-preserving move: each function is identical to its previous definition
in ``pre_pr.py``. ``pre_pr`` re-exports these names so existing imports keep
working.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _run_subprocess  # noqa: E402


def validate_review_marker(repo_root: Path) -> bool:
    """Advisory check for a SHA-bound ``Reviewed-By: /review@...`` marker on HEAD.

    Wraps ``scripts/validation/validate_review_marker.py`` (Issue #1938). The
    marker is the ``/ship`` precondition: it proves ``/review`` passed on the
    exact code being shipped. ``/ship`` itself blocks on a missing marker (AC1);
    here the check is **advisory** by default, because most pre-PR pushes are
    mid-development and have not run ``/review`` yet. Blocking every such push
    would break normal iteration.

    Set ``REVIEW_MARKER_ENFORCED=1`` to escalate to BLOCKING (returns False when
    HEAD has no binding marker). Mirrors the advisory/enforced pattern used by
    ``validate_command_bundle_coverage`` (``BUNDLE_CHECK_ENFORCED``).
    """
    enforced = os.environ.get("REVIEW_MARKER_ENFORCED", "").lower() in ("1", "true")

    script = repo_root / "scripts" / "validation" / "validate_review_marker.py"
    if not script.exists():
        if enforced:
            print("[FAIL] validate_review_marker.py not present")
            return False
        print("[WARN] validate_review_marker.py not found (advisory skip)")
        return True

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:20]:
            print(line)

    if exit_code == 0:
        return True

    if enforced:
        # exit 1 (no/stale marker) and exit 2 (config) both block in enforced mode.
        return False
    print(
        "  Note: advisory only (default). /ship blocks on this; pre_pr does not. "
        "Set REVIEW_MARKER_ENFORCED=1 to make it BLOCKING here. See Issue #1938."
    )
    return True


def validate_command_bundle_coverage(repo_root: Path) -> bool:
    """SPEC-005 advisory check: each lifecycle command invokes its bundled skills.

    Reads the canonical BUNDLE_REGISTRY from
    ``scripts/validation/bundle_registry.py`` and verifies that each
    ``.claude/commands/<file>`` contains the expected
    ``Skill(skill="...")`` invocation.

    Default behavior is **advisory** (returns True regardless of missing
    invocations; emits WARN findings). Set
    ``BUNDLE_CHECK_ENFORCED=1`` to escalate to BLOCKING (returns False
    on any missing invocation). Per SPEC-005 AC-14 and Q3 resolution.
    """
    enforced = os.environ.get("BUNDLE_CHECK_ENFORCED", "").lower() in ("1", "true")

    # Lazy import; sibling module under scripts/validation/.
    sys.path.insert(0, str(repo_root / "scripts" / "validation"))
    try:
        from bundle_registry import BUNDLE_REGISTRY, expected_skill_invocation
    except ImportError as exc:
        # Per SPEC-005 Q3: default is advisory. An import failure in advisory
        # mode must not block pre_pr; in enforced mode it is a hard fail.
        if enforced:
            print(f"[FAIL] Could not import bundle_registry: {exc}")
            return False
        print(f"[WARN] Could not import bundle_registry (advisory skip): {exc}")
        return True

    commands_dir = repo_root / ".claude" / "commands"

    missing: list[tuple[str, str]] = []
    for command_file, skill in BUNDLE_REGISTRY:
        path = commands_dir / command_file
        if not path.exists():
            missing.append((command_file, skill))
            continue
        text = path.read_text(encoding="utf-8")
        if expected_skill_invocation(skill) not in text:
            missing.append((command_file, skill))

    if not missing:
        print(f"[PASS] All {len(BUNDLE_REGISTRY)} bundle invocations present")
        return True

    label = "FAIL" if enforced else "WARN"
    mode = "blocking" if enforced else "advisory"
    print(f"[{label}] {len(missing)} bundle invocation(s) missing ({mode}):")
    for cmd, skill in missing:
        print(f"  - {cmd}: missing Skill(skill=\"{skill}\")")
    if not enforced:
        print(
            "  Note: advisory only (default). Set BUNDLE_CHECK_ENFORCED=1 "
            "to make this BLOCKING. See SPEC-005 AC-14."
        )
    return not enforced
