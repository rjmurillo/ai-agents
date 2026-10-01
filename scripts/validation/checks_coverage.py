#!/usr/bin/env python3
"""Review-marker coverage gate for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Holds the
advisory-by-default gate that reports on the SHA-bound ``/review`` marker.

Behavior-preserving move: the function is identical to its previous definition
in ``pre_pr.py``. ``pre_pr`` re-exports the name so existing imports keep
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

# The typed contract, package path (evidence.py states why).
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_SCRIPT_ABSENT,
    REASON_VIOLATIONS_FOUND,
    CheckOutcome,
)

_VALIDATOR = "validate_review_marker"
_SCOPE = "SHA-bound /review marker on HEAD"
_HEAD = "HEAD"

_FAIL_TOKEN = "[FAIL]"
_WARN_TOKEN = "[WARN]"


def _as_advisory(line: str) -> str:
    """Rewrite a leading ``[FAIL]`` token to ``[WARN]``.

    ``validate_review_marker.py`` writes ``[FAIL]`` because it blocks under
    ``/ship``. Forwarding that token from a caller that goes on to return True
    prints a blocking severity on a passing check, so the reader reconciles it
    against the ``RESULT:`` count at the bottom of the log (issue #4315).
    """
    stripped = line.lstrip()
    if not stripped.startswith(_FAIL_TOKEN):
        return line
    indent = line[: len(line) - len(stripped)]
    return indent + _WARN_TOKEN + stripped[len(_FAIL_TOKEN) :]


def _print_output(output: str, rewrite_fail_to_warn: bool = False) -> None:
    """Print up to 20 lines of subprocess output, optionally downgrading [FAIL].

    Printing happens on the exit path that knows the verdict, never before it.
    An earlier unconditional print forwarded the token before the severity was
    decided, and every branch below printed the same lines a second time.
    """
    for line in output.strip().splitlines()[:20]:
        print(_as_advisory(line) if rewrite_fail_to_warn else line)


def validate_review_marker(repo_root: Path) -> CheckOutcome:
    """Advisory check for a SHA-bound ``Reviewed-By: /review@...`` marker on HEAD.

    Wraps ``scripts/validation/validate_review_marker.py`` (Issue #1938). The
    marker is the ``/ship`` precondition: it proves ``/review`` passed on the
    exact code being shipped. ``/ship`` itself blocks on a missing marker (AC1);
    here the check is **advisory** by default, because most pre-PR pushes are
    mid-development and have not run ``/review`` yet. Blocking every such push
    would break normal iteration.

    Set ``REVIEW_MARKER_ENFORCED=1`` to escalate to BLOCKING (a non-passing
    check then blocks the push).

    Returns typed evidence (issue #5636). A valid marker is ``PASS``. Advisory
    mode reports a missing or stale marker, or a failed script run, as ``FAIL``
    with reason ``advisory.findings``, which ``pre_pr_policy`` licenses, and an
    absent script as ``SKIP``. Enforced mode reports the same conditions as
    unlicensed ``FAIL`` results, so they block exactly as ``False`` did.
    """
    enforced = os.environ.get("REVIEW_MARKER_ENFORCED", "").lower() in ("1", "true")

    script = repo_root / "scripts" / "validation" / "validate_review_marker.py"
    if not script.exists():
        return _absent_outcome(enforced)

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")

    if exit_code == 0:
        if output.strip():
            _print_output(output)
        return CheckOutcome.passed(_VALIDATOR, revision=_HEAD, scope=_SCOPE)

    if enforced:
        # exit 1 (no/stale marker) and exit 2 (config) both block in enforced mode.
        # Pass the script's output verbatim: [FAIL] is accurate here.
        if output.strip():
            _print_output(output)
        return CheckOutcome.failed(
            _VALIDATOR,
            reason=REASON_VIOLATIONS_FOUND,
            revision=_HEAD,
            scope=_SCOPE,
            detail=f"validate_review_marker.py exited {exit_code}; REVIEW_MARKER_ENFORCED is set",
        )

    # Advisory path: the check did not pass, but the caller will still not block.
    # Printing [FAIL] here is misleading because the overall run succeeds.
    # Rewrite [FAIL] tokens to [WARN] so the severity label matches the outcome.
    if output.strip():
        _print_output(output, rewrite_fail_to_warn=True)
    print(
        "  Note: advisory only (default). /ship blocks on this; pre_pr does not. "
        "Set REVIEW_MARKER_ENFORCED=1 to make it BLOCKING here. See Issue #1938."
    )
    # One fixed reason for every non-zero exit, not a classified one: a timeout
    # or signal reason would be unlicensed and start blocking a gate that never did.
    return CheckOutcome.failed(
        _VALIDATOR,
        reason=REASON_ADVISORY_FINDINGS,
        revision=_HEAD,
        scope=_SCOPE,
        detail=f"validate_review_marker.py exited {exit_code}; advisory, not enforced",
    )


def _absent_outcome(enforced: bool) -> CheckOutcome:
    """Type a missing validator script: unlicensed ``FAIL`` when enforced, else ``SKIP``."""
    if enforced:
        print("[FAIL] validate_review_marker.py not present")
        return CheckOutcome.failed(
            _VALIDATOR,
            reason=REASON_SCRIPT_ABSENT,
            scope=_SCOPE,
            detail="validate_review_marker.py not present and REVIEW_MARKER_ENFORCED is set",
        )
    print("[WARN] validate_review_marker.py not found (advisory skip)")
    return CheckOutcome.skipped(
        _VALIDATOR,
        reason=REASON_SCRIPT_ABSENT,
        scope=_SCOPE,
        detail="validate_review_marker.py not present; advisory skip",
    )
