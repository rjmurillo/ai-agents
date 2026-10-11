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
  EVENT_NAME           - github.event_name
  PR_NUMBER            - pull request number (workflow_dispatch body fetch)
  GITHUB_REPOSITORY    - owner/repo (workflow_dispatch body fetch)
  GH_TOKEN             - API token for the body fetch (falls back to GITHUB_TOKEN)
  GITHUB_API_URL       - API base, https only (default https://api.github.com)
  GITHUB_STEP_SUMMARY  - path to the step summary file (optional)

EXIT CODES (ADR-035):
  0 - PASS
  1 - FAIL: the pull request links a spec and its acceptance criteria are
      missing or unchecked
  2 - config error: HAS_SPECS is not "true" or "false", or a
      workflow_dispatch body fetch failed
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.external_signals.acceptance_criteria import (
    acceptance_heading_count,
    hidden_unchecked,
    parse_criteria,
)
from scripts.external_signals.markdown_visibility import unclosed_construct

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2

CHECK_NAME = "Validate Spec Coverage"
ACCEPTANCE_HEADING = "## Acceptance criteria"
_DISPATCH_EVENT = "workflow_dispatch"
_FETCH_TIMEOUT_SECONDS = 60
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


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect, so the bearer token never reaches another URL.

    The default handler forwards the Authorization header to the redirect
    target. Returning None makes urllib raise HTTPError on the 3xx instead.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirect)
_DEFAULT_API_URL = "https://api.github.com"
_PR_NUMBER = re.compile(r"[1-9][0-9]*")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# GitHub shows about ten annotations per step. Leave room for the verdict line.
_MAX_ITEM_ANNOTATIONS = 8


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
        return Verdict(
            False,
            "The pull request links a spec but its body has no acceptance "
            f"checkbox section. Add a `{ACCEPTANCE_HEADING}` heading with "
            "`- [ ]` or `- [x]` items.",
        )
    unchecked = [c.text for c in criteria if not c.checked]
    if unchecked:
        return Verdict(
            False,
            f"{len(unchecked)} of {len(criteria)} acceptance criteria are unchecked.",
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


def _pull_request_url(pr_number: str, repository: str) -> str | None:
    """Build the pull request API URL from validated inputs, or None."""
    api_url = os.environ.get("GITHUB_API_URL", "") or _DEFAULT_API_URL
    if not _PR_NUMBER.fullmatch(pr_number):
        _fetch_error(f"PR_NUMBER must be a positive integer, got {pr_number!r}.")
    elif not _REPOSITORY.fullmatch(repository) or {".", ".."} & set(repository.split("/")):
        _fetch_error(f"GITHUB_REPOSITORY must be owner/repo, got {repository!r}.")
    elif not api_url.startswith("https://"):
        _fetch_error("GITHUB_API_URL must start with https://.")
    else:
        return f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}"
    return None


def _read_body_field(url: str) -> str | None:
    """GET the pull request and return its body ('' when null), or None on failure."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _OPENER.open(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read())
    except (OSError, ValueError) as exc:
        # HTTPError and URLError are OSError; bad JSON or bytes are ValueError.
        _fetch_error(f"reading the pull request failed: {exc}")
        return None
    if not isinstance(payload, dict) or "body" not in payload:
        _fetch_error("the pull request response has no body field.")
        return None
    body = payload["body"]
    if body is not None and not isinstance(body, str):
        _fetch_error("the pull request body field is not text.")
        return None
    return body or ""


def _fetch_body(pr_number: str, repository: str) -> str | None:
    """Read the pull request body over the GitHub REST API. None means failure."""
    url = _pull_request_url(pr_number, repository)
    return None if url is None else _read_body_field(url)


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
    if not body and os.environ.get("EVENT_NAME", "") == _DISPATCH_EVENT:
        fetched = _fetch_body(
            os.environ.get("PR_NUMBER", ""), os.environ.get("GITHUB_REPOSITORY", "")
        )
        if fetched is None:
            return _config_error(
                "Could not read the pull request body for this workflow_dispatch "
                "run; see the log for the error."
            )
        body = fetched
    verdict = decide(has_specs, body)
    _report(verdict)
    return EXIT_OK if verdict.passed else EXIT_FAIL


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
