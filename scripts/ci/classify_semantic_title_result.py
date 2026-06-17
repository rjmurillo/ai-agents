#!/usr/bin/env python3
"""Classify the outcome of the semantic-PR-title-check action (issue #2616).

This is the decision half of `.github/workflows/semantic-pr-title-check.yml`.
The workflow runs `amannn/action-semantic-pull-request` with
`continue-on-error: true`, then calls this script to decide whether the job
should pass or fail. Keeping the decision here (ADR-006: no logic in YAML) lets
it be tested.

Why this exists: on PR #2611 the action failed because GitHub returned its
"Unicorn!" HTML error page instead of an API response while the action was
fetching PR data. The PR title was valid; rerunning recovered without changing
it. The required "Validate PR title" job must not fail on that transient
infrastructure flake, but it must still fail on a genuine bad title.

Discriminator (Layer 1, the action's own contract):
`amannn/action-semantic-pull-request` sets its `error_message` step output
from `raiseError()` BEFORE the step fails, but only when a validation gate
fails (missing type, unknown scope, subject pattern, etc.). A network crash
inside the action throws before any gate runs, so `error_message` stays empty.
Therefore:

    outcome == success/skipped              -> pass (exit 0)
    outcome == failure, error_message set   -> real bad title, block (exit 1)
    outcome == failure, error_message empty -> transient flake, pass (exit 0)

The Unicorn HTML marker in an optional ``--log-file`` is a secondary positive
signal used only to label the transient case in output; the workflow does not
currently pass a log file. The decision keys on whether the action reported a
semantic reason.

Exit Codes (ADR-035):
    0 = pass (valid title, success, or transient infra flake)
    1 = block (genuine semantic-title validation failure)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

# Marker GitHub serves on its HTML error page (the "Unicorn!" page). Used only
# to label a transient failure in output, not to drive the pass/fail decision.
_UNICORN_MARKER = "<title>Unicorn"

# Outcomes (GitHub Actions `steps.<id>.outcome`) that mean the action did not
# report a bad title and the job should pass.
_PASSING_OUTCOMES = frozenset({"success", "skipped"})


@dataclass(frozen=True)
class Classification:
    """The pass/fail decision plus the reason to surface in the job log."""

    exit_code: int
    is_semantic_failure: bool
    is_transient: bool
    message: str


def classify(*, outcome: str, error_message: str, log: str) -> Classification:
    """Decide whether the title-check job should pass or fail.

    Args:
        outcome: GitHub Actions step outcome of the action
            ("success", "failure", "skipped", "cancelled").
        error_message: The action's `error_message` output. Non-empty only when
            a real semantic-title validation gate failed.
        log: Captured stdout/stderr of the action step, used only to label a
            transient failure.

    Returns:
        A Classification carrying the exit code and a human-readable message.
    """
    if outcome in _PASSING_OUTCOMES:
        return Classification(
            exit_code=0,
            is_semantic_failure=False,
            is_transient=False,
            message=f"PR title check passed (outcome={outcome}).",
        )

    reason = error_message.strip()
    if reason:
        return Classification(
            exit_code=1,
            is_semantic_failure=True,
            is_transient=False,
            message=reason,
        )

    # Failure with no semantic reason: the action crashed before any validation
    # gate ran. This is the Unicorn HTML flake or another transient infra error.
    if _UNICORN_MARKER in log:
        detail = "GitHub returned its Unicorn HTML error page"
    else:
        detail = "the action failed without a semantic-title reason"
    return Classification(
        exit_code=0,
        is_semantic_failure=False,
        is_transient=True,
        message=(
            f"Transient infrastructure failure ({detail}); "
            "not a PR title defect. Rerun to recover."
        ),
    )


def _read_log(log_file: str | None) -> str:
    """Read the captured action log, tolerating a missing file."""
    if not log_file:
        return ""
    base_dir = Path(__file__).resolve().parents[2]
    path = Path(log_file)
    if not path.is_absolute():
        path = base_dir / path
    try:
        path = path.resolve()
        path.relative_to(base_dir)
    except (OSError, ValueError):
        return ""
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _render(result: Classification, pr_title: str) -> str:
    """Build the operator-facing message echoing the PR title and verdict."""
    lines = [f"PR title: {pr_title}"]
    if result.is_semantic_failure:
        lines.append("Result: FAIL (semantic title validation)")
        lines.append(f"Reason: {result.message}")
    elif result.is_transient:
        lines.append("Result: PASS (transient infrastructure flake, not blocking)")
        lines.append(f"Detail: {result.message}")
    else:
        lines.append("Result: PASS")
        lines.append(f"Detail: {result.message}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the exit code (0 pass, 1 block)."""
    parser = argparse.ArgumentParser(
        description="Classify semantic-PR-title-check action outcome (issue #2616)."
    )
    parser.add_argument("--outcome", required=True, help="Action step outcome.")
    parser.add_argument(
        "--error-message",
        default="",
        help="The action's error_message output (empty unless a real bad title).",
    )
    parser.add_argument("--pr-title", default="", help="The PR title under check.")
    parser.add_argument(
        "--log-file",
        default=None,
        help="Path to the captured action log (used to label transient flakes).",
    )
    args = parser.parse_args(argv)

    log = _read_log(args.log_file)
    result = classify(
        outcome=args.outcome, error_message=args.error_message, log=log
    )
    print(_render(result, args.pr_title))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
