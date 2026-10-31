#!/usr/bin/env python3
"""Decide the Validate Spec Coverage verdict from the PR body alone.

Issue #6182. The check used to take its verdict from two model calls, so a
credit, token, or quota failure turned it red or green regardless of the pull
request. The verdict is now a pure function of two inputs: whether the pull
request links a spec, and the acceptance-criteria checkboxes in its body.

Decision table (SPEC-6182):

  has_specs  acceptance section        verdict
  ---------  ------------------------  ----------------------------
  false      any                       PASS (no linked spec)
  true       absent or no checkboxes   FAIL (names the heading)
  true       any box unchecked         FAIL (lists each unchecked)
  true       all boxes checked         PASS

The parser is ``scripts/external_signals/acceptance_criteria.py``, which uses
only the standard library, so this script runs under bare ``python3``
(``.claude/rules/ci-scripts.md`` MUST 18).

ENV:
  HAS_SPECS            - "true" or "false", from the Extract Spec References step
  PR_BODY              - pull request body (author-controlled; read from env,
                         never interpolated into a shell, CWE-78)
  PR_BODY_FILE         - path to the body the Extract Spec References step read,
                         so both steps grade one body. Used when PR_BODY is
                         empty. This script never fetches a body itself.
  EVENT_NAME           - github.event_name
  GITHUB_STEP_SUMMARY  - path to the step summary file (optional)

EXIT CODES (ADR-035):
  0 - PASS
  1 - FAIL: the pull request links a spec and its acceptance criteria are
      missing or unchecked
  2 - config error: HAS_SPECS is not "true" or "false", PR_BODY_FILE is
      unreadable, or workflow_dispatch ran with no PR_BODY and no PR_BODY_FILE
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.external_signals.acceptance_criteria import (
    acceptance_heading_count,
    has_acceptance_section,
    hidden_unchecked,
    near_miss_headings,
    parse_criteria,
)
from scripts.external_signals.markdown_visibility import unclosed_construct

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2

CHECK_NAME = "Validate Spec Coverage"
ACCEPTANCE_HEADING = "## Acceptance criteria"
_DISPATCH_EVENT = "workflow_dispatch"
_UNCLOSED_REASONS = {
    "comment": (
        "The pull request body has an HTML comment (`<!--`) with no closing `-->`. "
        "It can hide acceptance boxes, so the check fails closed. Close the comment."
    ),
    "fence": (
        "The pull request body has a code fence with no closing fence. It can hide "
        "acceptance boxes, so the check fails closed. Close the fence."
    ),
}


# GitHub shows about ten annotations per step. Leave room for the verdict line.
_MAX_ITEM_ANNOTATIONS = 8


_ITEM_SYNTAX = "`- [ ] text` or `- [x] text`"
_UNCHECKED_HINT = (
    " Check each box once the work is done. For a criterion the owner deferred, "
    "move it under a separate heading at the same or a higher level than your "
    "acceptance heading (a lower-level heading stays inside the section and its "
    "boxes still count), such as `## Deferred` under `## Acceptance criteria`, "
    "and link the follow-up."
)


def _no_criteria_reason(body: str) -> str:
    """Say what the parser needs and what it found instead, for a body with no boxes."""
    reason = (
        "The pull request links a spec but its body has no acceptance checkbox "
        f"section. The check needs a heading that reads exactly `{ACCEPTANCE_HEADING}` "
        f"(any `#` level, nothing else on the line) followed by items written as "
        f"{_ITEM_SYNTAX}."
    )
    if has_acceptance_section(body):
        reason += (
            " The heading is present but has no checkbox items under it. Numbered "
            "lists (`1. text`) and bullets without brackets do not count."
        )
    else:
        near = near_miss_headings(body)
        if near:
            reason += f" Found `{near[0]}`, which the check does not accept. Rename it."
    return reason


@dataclass(frozen=True)
class Verdict:
    """Outcome of the check: pass or fail, a reason, and any unchecked items."""

    passed: bool
    reason: str
    unchecked: list[str] = field(default_factory=list)


def decide(has_specs: bool, body: str) -> Verdict:
    """Return the verdict for a pull request. Pure: same inputs, same output."""
    if not has_specs:
        return Verdict(True, "No linked spec, nothing to cover.")
    unclosed = unclosed_construct(body)
    if unclosed:
        return Verdict(False, _UNCLOSED_REASONS[unclosed])
    if acceptance_heading_count(body) > 1:
        return Verdict(
            False,
            "The pull request body has more than one acceptance heading. Keep one "
            f"`{ACCEPTANCE_HEADING}` section so the check grades the one GitHub shows.",
        )
    hidden = hidden_unchecked(body)
    if hidden:
        return Verdict(
            False,
            f"{len(hidden)} unchecked acceptance box(es) are hidden inside an HTML "
            "comment or code block, where GitHub may still show them. Move them out "
            "of the comment or block, or delete them.",
            hidden,
        )
    criteria = parse_criteria(body)
    if not criteria:
        return Verdict(False, _no_criteria_reason(body))
    unchecked = [c.text for c in criteria if not c.checked]
    if unchecked:
        return Verdict(
            False,
            f"{len(unchecked)} of {len(criteria)} acceptance criteria are unchecked."
            + _UNCHECKED_HINT,
            unchecked,
        )
    return Verdict(True, f"All {len(criteria)} acceptance criteria are checked.")


def _parse_has_specs(raw: str) -> bool | None:
    """Return True or False for the two accepted spellings, None otherwise."""
    value = raw.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _fetch_error(message: str) -> None:
    print(f"::error::{_escape_annotation(message)}", file=sys.stderr)


def _read_body_file(path: str) -> str | None:
    """Read the body the Extract Spec References step saved. None means failure.

    That step appends one newline when it writes the file, so exactly one is
    removed here and a body that itself ends in newlines comes back unchanged.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        _fetch_error(f"reading the saved pull request body failed: {exc}")
        return None
    return text[:-1] if text.endswith("\n") else text


def _format_summary(verdict: Verdict) -> str:
    label = "PASS" if verdict.passed else "FAIL"
    lines = [f"### {CHECK_NAME}: {label}", "", verdict.reason]
    if verdict.unchecked:
        lines += ["", "Unchecked acceptance criteria:"]
        lines += [f"- [ ] {item}" for item in verdict.unchecked]
    return "\n".join(lines) + "\n"


def _escape_annotation(text: str) -> str:
    """Escape text for a workflow command: ``%``, CR, and LF (GitHub's rules)."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _write_summary(text: str) -> None:
    """Append to the step summary. A write failure warns and never changes the verdict."""
    path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as exc:
        print(f"::warning::could not write the step summary: {exc}", file=sys.stderr)


def _annotate_unchecked(unchecked: list[str]) -> None:
    for item in unchecked[:_MAX_ITEM_ANNOTATIONS]:
        print(f"::error::{_escape_annotation('Unchecked acceptance criterion: ' + item)}")
    hidden = len(unchecked) - _MAX_ITEM_ANNOTATIONS
    if hidden > 0:
        print(f"::error::{hidden} more unchecked criteria are listed in the step summary.")


def _report(verdict: Verdict) -> None:
    label = "PASS" if verdict.passed else "FAIL"
    print(f"{CHECK_NAME}: {label}. {verdict.reason}")
    for item in verdict.unchecked:
        print(f"  unchecked: {item}")
    _annotate_unchecked(verdict.unchecked)
    if not verdict.passed:
        print(f"::error::{_escape_annotation(f'{CHECK_NAME}: {verdict.reason}')}")
    _write_summary(_format_summary(verdict))


def _config_error(message: str) -> int:
    """Report a config error on stderr and in a one-line step summary."""
    print(f"::error::{_escape_annotation(message)}", file=sys.stderr)
    _write_summary(f"### {CHECK_NAME}: ERROR\n\n{message}\n")
    return EXIT_CONFIG


def run() -> int:
    """Read the environment, decide, report, and return the exit code."""
    has_specs = _parse_has_specs(os.environ.get("HAS_SPECS", ""))
    if has_specs is None:
        return _config_error(
            'HAS_SPECS must be "true" or "false"; the Extract Spec References step did not emit it.'
        )
    body = os.environ.get("PR_BODY", "")
    body_file = os.environ.get("PR_BODY_FILE", "")
    if not body and body_file:
        saved = _read_body_file(body_file)
        if saved is None:
            return _config_error(
                "Could not read the pull request body the Extract Spec References "
                "step saved; see the log for the error."
            )
        body = saved
    elif not body and os.environ.get("EVENT_NAME", "") == _DISPATCH_EVENT:
        return _config_error(
            "PR_BODY_FILE missing; the Extract Spec References step did not emit pr_body_file."
        )
    verdict = decide(has_specs, body)
    _report(verdict)
    return EXIT_OK if verdict.passed else EXIT_FAIL


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
