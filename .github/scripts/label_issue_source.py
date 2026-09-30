#!/usr/bin/env python3
"""Apply exactly one ``source:*`` provenance label to a newly opened issue.

Epic #5698, acceptance criterion AC-3 (spec:
``.project-toolkit/specs/SPEC-agent-backlog-provenance.md``, criterion 3). The
``new_issue.py --source`` flag (#5700) only sees issues filed through that
script. This labeler runs on ``issues.opened`` and sees every door: the MCP
tool, raw ``gh issue create``, workflows, and the web form.

Decision rule, from the spec:

- ``source:agent`` when the author is a bot (login ends in ``[bot]``, is
  ``github-actions``, or the API reports user type ``Bot``).
- ``source:agent`` when the author is the repository owner and the body carries
  no human marker. The owner login is shared with every agent session, so the
  default is agent: only a human can assert human.
- ``source:human`` when the author is the repository owner and the body ends
  with ``<!-- source:human -->`` as its last non-blank line and the issue is not
  part of a burst (another issue by the same login in the previous ten
  minutes). A burst forces ``source:agent`` whatever the marker says. The
  burst check looks backward only, so the first issue of a burst is not caught.
- ``source:agent`` when the author is missing (a deleted account).
- ``source:human`` when the author is any other person.

Trust boundary: the issue body is untrusted input. It is fetched by this script
through the API, never interpolated into a shell command or a workflow
expression, and it is only searched for the marker. Every ``gh`` call uses an
argument list with no shell.

Different than the spec: the spec's web-form hidden field is not implemented
because this repository has no issue form. The spec's close-as-not-planned
behavior for agent issues without Step 0 answers is not implemented here. This
script only labels.

Residual risk, recorded in the spec: under a shared login no in-band marker is
unforgeable. The burst rule is a detective control, not a preventive one. An
agent that writes the marker as the last line of an issue body, outside a burst,
receives ``source:human``. ``new_issue.py`` rejects that body for ``--source
agent``, but raw ``gh`` and the MCP tool cannot be stopped from writing it.

Exit codes (AGENTS.md, ADR-035): 0 ok, 2 config error, 3 external error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import quote

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

LABEL_HUMAN = "source:human"
LABEL_AGENT = "source:agent"
SOURCE_LABELS = (LABEL_HUMAN, LABEL_AGENT)

# Written by new_issue.py on --source human, always as the last line. The two
# literals are kept equal by tests/test_label_issue_source.py because a skill
# script cannot import from .github/scripts and stay self-contained in an
# installed plugin.
HUMAN_MARKER_PATTERN = re.compile(r"<!--\s*source:human\s*-->", re.IGNORECASE)

BURST_WINDOW = timedelta(minutes=10)
_GH_TIMEOUT_SECONDS = 30
_NAME_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_LABEL_COLORS = {LABEL_HUMAN: "0e8a16", LABEL_AGENT: "d93f0b"}
_LABEL_DESCRIPTIONS = {
    LABEL_HUMAN: "A human selected this work",
    LABEL_AGENT: "An agent selected this work",
}


class GhError(RuntimeError):
    """A gh call failed. Carries the trimmed stderr."""


def is_bot(login: str, user_type: str) -> bool:
    """Return True when the author is an automation identity."""
    lowered = login.lower()
    return lowered.endswith("[bot]") or lowered == "github-actions" or user_type == "Bot"


def has_human_marker(body: str) -> bool:
    """Return True when the marker is the last non-blank line of the raw body.

    Anchoring to the last line means a marker quoted in prose, or in a fenced
    example inside an issue about this labeler, does not count.
    """
    lines = [line for line in (body or "").splitlines() if line.strip()]
    return bool(lines) and HUMAN_MARKER_PATTERN.fullmatch(lines[-1].strip()) is not None


def classify(login: str, user_type: str, owner: str, body: str, in_burst: bool) -> tuple[str, str]:
    """Return ``(label, reason)`` for one issue. Pure, no network."""
    if not login:
        return LABEL_AGENT, "author is missing"
    if is_bot(login, user_type):
        return LABEL_AGENT, "author is an automation identity"
    if login.lower() != owner.lower():
        return LABEL_HUMAN, "author is not the repository owner"
    if not has_human_marker(body):
        return LABEL_AGENT, "owner login without a human marker defaults to agent"
    if in_burst:
        return LABEL_AGENT, "human marker ignored inside a burst"
    return LABEL_HUMAN, "owner login with a human marker outside a burst"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_in_burst(current: dict[str, Any], others: list[dict[str, Any]]) -> bool:
    """Return True when another issue by the same login opened in the window."""
    opened = _parse_time(current["created_at"])
    for other in others:
        if other.get("number") == current.get("number") or "pull_request" in other:
            continue
        gap = opened - _parse_time(other["created_at"])
        if timedelta(0) <= gap <= BURST_WINDOW:
            return True
    return False


def _error_text(result: subprocess.CompletedProcess[str]) -> str:
    """Join stderr and stdout: ``gh api`` puts the JSON error body on stdout.

    Newlines and ``::`` are removed so the text cannot forge a workflow command
    when it is printed after ``::error::`` or ``::warning::``.
    """
    joined = f"{result.stderr.strip()} {result.stdout.strip()}".strip()
    return " ".join(joined.split()).replace("::", ": :")[:300]


def _valid_name(value: str) -> bool:
    return _NAME_PATTERN.fullmatch(value) is not None and value not in {".", ".."}


def _gh(args: list[str]) -> str:
    """Run gh with an argument list. Return stdout or raise GhError."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GhError(str(exc)) from exc
    if result.returncode != 0:
        raise GhError(_error_text(result))
    return result.stdout


def fetch_issue(owner: str, repo: str, number: int) -> dict[str, Any]:
    """Fetch the issue, including its untrusted body."""
    return cast("dict[str, Any]", json.loads(_gh(["api", f"repos/{owner}/{repo}/issues/{number}"])))


def fetch_recent_by_author(
    owner: str, repo: str, login: str, since: datetime
) -> list[dict[str, Any]]:
    """Fetch every page of issues by ``login`` updated since ``since``.

    The endpoint sorts by creation time, newest first. Issues opened after the
    current one sort ahead of the window, so a single page could push a
    qualifying older issue onto page two. ``--paginate --slurp`` returns all
    pages as a list of lists, which this function flattens.
    """
    stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    endpoint = (
        f"repos/{owner}/{repo}/issues?state=all&per_page=100"
        f"&creator={quote(login, safe='')}&since={stamp}"
    )
    pages = cast(
        "list[list[dict[str, Any]]]", json.loads(_gh(["api", "--paginate", "--slurp", endpoint]))
    )
    return [item for page in pages for item in page]


def ensure_label(owner: str, repo: str, label: str) -> None:
    """Create the label when missing. An existing label is not an error."""
    try:
        _gh(
            [
                "api",
                "-X",
                "POST",
                f"repos/{owner}/{repo}/labels",
                "-f",
                f"name={label}",
                "-f",
                f"color={_LABEL_COLORS[label]}",
                "-f",
                f"description={_LABEL_DESCRIPTIONS[label]}",
            ]
        )
    except GhError as exc:
        if "already_exists" not in str(exc) and "already exists" not in str(exc):
            raise


def apply_label(owner: str, repo: str, number: int, desired: str, current: list[str]) -> None:
    """Make ``desired`` the only source label on the issue.

    The desired label is added before the stale one is removed, so a failure
    between the calls leaves two source labels, never none.
    """
    ensure_label(owner, repo, desired)
    if desired not in current:
        _gh(
            [
                "api",
                "-X",
                "POST",
                f"repos/{owner}/{repo}/issues/{number}/labels",
                "-f",
                f"labels[]={desired}",
            ]
        )
    for stale in (name for name in SOURCE_LABELS if name != desired and name in current):
        _gh(
            [
                "api",
                "-X",
                "DELETE",
                f"repos/{owner}/{repo}/issues/{number}/labels/{quote(stale, safe='')}",
            ]
        )


def _burst_state(owner: str, repo: str, issue: dict[str, Any], login: str) -> bool:
    """Look up burst state. A failed lookup fails toward agent and says so."""
    since = _parse_time(issue["created_at"]) - BURST_WINDOW
    try:
        others = fetch_recent_by_author(owner, repo, login, since)
    except (GhError, json.JSONDecodeError) as exc:
        print(f"::warning::burst lookup failed, treating as burst: {exc}", flush=True)
        return True
    return is_in_burst(issue, others)


def label_issue(owner: str, repo: str, number: int) -> tuple[str, str]:
    """Label one issue. Returns ``(label, reason)``."""
    issue = fetch_issue(owner, repo, number)
    user = issue.get("user") or {}
    login = str(user.get("login", ""))
    body = str(issue.get("body") or "")
    marker_candidate = (
        not is_bot(login, str(user.get("type", "")))
        and login.lower() == owner.lower()
        and has_human_marker(body)
    )
    in_burst = _burst_state(owner, repo, issue, login) if marker_candidate else False
    label, reason = classify(login, str(user.get("type", "")), owner, body, in_burst)
    current = [str(item.get("name", "")) for item in issue.get("labels", [])]
    apply_label(owner, repo, number, label, current)
    return label, reason


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument("--owner", required=True, help="Repository owner login")
    parser.add_argument("--repo", required=True, help="Repository name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.issue < 1 or not _valid_name(args.owner) or not _valid_name(args.repo):
        print("Invalid --issue, --owner, or --repo", file=sys.stderr)
        return EXIT_CONFIG
    try:
        label, reason = label_issue(args.owner, args.repo, args.issue)
    except (GhError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"::error::Could not label issue #{args.issue}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(f"Issue #{args.issue} labeled {label}: {reason}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
