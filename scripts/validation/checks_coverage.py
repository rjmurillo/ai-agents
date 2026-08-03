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


def validate_review_marker(repo_root: Path) -> bool:
    """Advisory check for a SHA-bound ``Reviewed-By: /review@...`` marker on HEAD.

    Wraps ``scripts/validation/validate_review_marker.py`` (Issue #1938). The
    marker is the ``/ship`` precondition: it proves ``/review`` passed on the
    exact code being shipped. ``/ship`` itself blocks on a missing marker (AC1);
    here the check is **advisory** by default, because most pre-PR pushes are
    mid-development and have not run ``/review`` yet. Blocking every such push
    would break normal iteration.

    Set ``REVIEW_MARKER_ENFORCED=1`` to escalate to BLOCKING (returns False when
    HEAD has no binding marker).
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
        # Decide the severity before forwarding, not after. Under
        # REVIEW_MARKER_ENFORCED the wrapped script's [FAIL] is accurate and
        # travels verbatim; otherwise this call returns True and the token
        # would describe a failure that is not one.
        for line in output.strip().splitlines()[:20]:
            print(line if enforced else _as_advisory(line))

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
