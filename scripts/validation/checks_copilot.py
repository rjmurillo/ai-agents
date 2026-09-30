#!/usr/bin/env python3
"""Copilot-specific validation wrappers for the pre-PR runner."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
for _path in (_SCRIPT_DIR, _PROJECT_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from check_copilot_routing_exclusions import (  # noqa: E402
    validate_copilot_routing_exclusions as _validate_module,
)

# The typed contract, package path (evidence.py states why).
from scripts.validation.evidence import (  # noqa: E402
    REASON_TREE_ABSENT,
    REASON_VALIDATOR_RAISED,
    REASON_VIOLATIONS_FOUND,
    WORKING_TREE,
    CheckOutcome,
)

_VALIDATOR = "validate_copilot_routing_exclusions"
_SCOPE = "shipped Copilot skill files against the copilot-cli excluded skill names"


def validate_copilot_routing_exclusions(repo_root: Path) -> CheckOutcome:
    """Return typed evidence about Copilot skills routing to excluded skills.

    Typed (issue #5636). A clean scan is ``PASS``. A violation is ``FAIL`` with
    reason ``violations.found``. A skill file that is not found during the scan is
    ``SKIP`` with reason ``tree.absent``, which stays non-blocking exactly as the
    old ``True`` did. Any other raise, including a missing template (which raises
    ``RoutingConfigError``) and a malformed config, is ``FAIL`` with reason
    ``validator.raised`` and blocks, as ``False`` did.
    """
    try:
        clean = _validate_module(repo_root)
    except FileNotFoundError as exc:
        # A missing template raises RoutingConfigError, which the handler below
        # turns into a blocking FAIL. This branch is a skill file that vanished
        # or was unreadable mid-scan, non-blocking as it always was, so the message
        # names the path the OS reported instead of claiming which file it was.
        print(f"[WARNING] Copilot routing exclusion check skipped, file not found: {exc}")
        return CheckOutcome.skipped(
            _VALIDATOR,
            reason=REASON_TREE_ABSENT,
            scope=_SCOPE,
            detail=f"file not found: {exc.filename or exc}",
        )
    except Exception as exc:
        print(f"[ERROR] copilot routing exclusion check failed: {exc}", file=sys.stderr)
        return CheckOutcome.failed(
            _VALIDATOR,
            reason=REASON_VALIDATOR_RAISED,
            scope=_SCOPE,
            detail=f"{type(exc).__name__}: {exc}",
        )
    if clean:
        return CheckOutcome.passed(_VALIDATOR, revision=WORKING_TREE, scope=_SCOPE)
    return CheckOutcome.failed(
        _VALIDATOR,
        reason=REASON_VIOLATIONS_FOUND,
        revision=WORKING_TREE,
        scope=_SCOPE,
        detail="a shipped Copilot skill routes to an excluded skill",
    )
