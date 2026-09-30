#!/usr/bin/env python3
"""Report the agent-share circuit breaker. Report only: nothing is enforced.

Epic #5698, acceptance criterion AC-8 (spec:
``.project-toolkit/specs/SPEC-agent-backlog-provenance.md``, criterion 8):

    "While the trailing-7-day ``source:agent`` share exceeds 50 percent, the
    labeler shall close any newly opened agent-sourced issue as not planned with
    a comment naming the epic and the threshold, until the owner posts a reset
    comment on the epic."

The owner decided D7: fix AC-8 as a report. This script computes the share and
prints what the breaker would do. It never closes, labels, or comments on an
issue. The GitHub token it runs with needs ``issues: read`` only.

Rules:

- Window: issues (never pull requests) created in the 7 days ending at the
  creation time of the triggering issue. The triggering issue is inside it.
- Share: ``source:agent`` issues divided by issues that carry a ``source:*``
  label. Unlabeled issues are excluded from both sides. An issue carrying both
  labels (the labeler adds one before removing the other, so this is transient)
  counts as agent, the same fail-toward-agent default the labeler uses.
- Tripped: strictly more than 50 percent. Exactly 50 percent is not tripped. An
  empty window has no share and is not tripped.
- Would close: the triggering issue, when the breaker is tripped and that issue
  is labeled ``source:agent``. The breaker names "any newly opened agent-sourced
  issue", and this script runs once per opened issue.
- Reset: an owner comment on the epic with a line equal to ``RESET_TOKEN``.
  Comments by other logins, by bots, or with the token inside a longer line are
  counted as ignored. A reset is detected and reported. It is never applied, so
  ``would close`` is computed as if no reset existed.

Open owner questions (not decided here, so not enforced): whether a reset
lasts once or for 7 days; what counts as human versus agent when the owner and
the agents share one login; whether the first issue of a burst escapes.

Residual risk: the owner login is shared with every agent session, so an agent
can post the reset token. A token inside a fenced code block is also matched.

Different than ``label_issue_source.py``: that script writes labels and needs
``issues: write``. This one only reads. It defines its own ``gh`` wrapper
because ``label_issue_source._gh`` runs text-mode subprocesses without an
explicit encoding. It reuses ``GhError``, ``LABEL_*``, and ``is_bot`` from that
script unchanged.

Exit codes (AGENTS.md, ADR-035): 0 ok, 2 config error, 3 external error. A
tripped breaker exits 0: the report is informational.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from label_issue_source import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    LABEL_AGENT,
    LABEL_HUMAN,
    GhError,
    is_bot,
)

DEFAULT_EPIC = 5698
WINDOW = timedelta(days=7)
THRESHOLD_PERCENT = 50
RESET_TOKEN = "AC8-BREAKER-RESET"
_GH_TIMEOUT_SECONDS = 60
_NAME_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_LOGIN_UNSAFE = re.compile(r"[^A-Za-z0-9\-\[\]_]")


@dataclass(frozen=True, slots=True)
class Share:
    """Counts of labeled issues in the window and the agent-sourced numbers."""

    agent: int
    human: int
    agent_numbers: tuple[int, ...]

    @property
    def total(self) -> int:
        return self.agent + self.human

    @property
    def percent(self) -> float | None:
        return None if self.total == 0 else 100 * self.agent / self.total

    @property
    def tripped(self) -> bool:
        """Strictly above the threshold. Integer math avoids float edge cases."""
        return self.total > 0 and self.agent * 100 > THRESHOLD_PERCENT * self.total


@dataclass(frozen=True, slots=True)
class ResetScan:
    """Owner reset comments found, and how many token comments were ignored."""

    valid: tuple[dict[str, Any], ...]
    ignored: int
    ignored_logins: tuple[str, ...]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def source_of(issue: dict[str, Any]) -> str | None:
    """Return LABEL_AGENT, LABEL_HUMAN, or None for an unlabeled issue."""
    names = {str(item.get("name", "")) for item in issue.get("labels") or []}
    if LABEL_AGENT in names:
        return LABEL_AGENT
    if LABEL_HUMAN in names:
        return LABEL_HUMAN
    return None


def in_window(issue: dict[str, Any], anchor: datetime) -> bool:
    """True for a non-PR issue created in ``(anchor - 7 days, anchor]``."""
    if "pull_request" in issue:
        return False
    created = parse_time(issue["created_at"])
    return anchor - WINDOW < created <= anchor


def compute_share(issues: list[dict[str, Any]], anchor: datetime) -> Share:
    """Count labeled issues in the window. Later duplicates by number are dropped."""
    seen: set[int] = set()
    agent_numbers: list[int] = []
    human = 0
    for issue in issues:
        number = int(issue["number"])
        if number in seen or not in_window(issue, anchor):
            continue
        seen.add(number)
        source = source_of(issue)
        if source == LABEL_AGENT:
            agent_numbers.append(number)
        elif source == LABEL_HUMAN:
            human += 1
    return Share(len(agent_numbers), human, tuple(sorted(agent_numbers)))


def has_reset_token(body: str) -> bool:
    """True when a whole line, stripped, equals the token. Case-sensitive."""
    return any(line.strip() == RESET_TOKEN for line in (body or "").splitlines())


def _safe_login(login: str) -> str:
    return _LOGIN_UNSAFE.sub("?", login)[:40]


def find_resets(comments: list[dict[str, Any]], owner: str) -> ResetScan:
    """Split token-bearing comments into owner resets and ignored ones."""
    valid: list[dict[str, Any]] = []
    ignored: list[str] = []
    for comment in comments:
        if not has_reset_token(str(comment.get("body") or "")):
            continue
        user = comment.get("user") or {}
        login = str(user.get("login", ""))
        is_owner = login.lower() == owner.lower() and not is_bot(login, str(user.get("type", "")))
        if is_owner:
            valid.append(comment)
        else:
            ignored.append(_safe_login(login))
    return ResetScan(tuple(valid), len(ignored), tuple(sorted(set(ignored))))


def would_close(share: Share, trigger: dict[str, Any]) -> tuple[int, ...]:
    """Issue numbers the breaker would close. Empty unless tripped and agent."""
    if share.tripped and source_of(trigger) == LABEL_AGENT:
        return (int(trigger["number"]),)
    return ()


def _percent_text(share: Share) -> str:
    if share.percent is None:
        return "n/a (no labeled issues in the window)"
    return f"{share.percent:.1f}% ({share.agent} agent of {share.total} labeled)"


def _reset_lines(resets: ResetScan, epic: int) -> list[str]:
    lines = []
    if resets.valid:
        latest = max(resets.valid, key=lambda item: item["created_at"])
        lines.append(
            f"- reset: detected, latest by owner at {latest['created_at']} "
            f"({latest.get('html_url', 'no url')}). Reported only, not applied."
        )
    else:
        lines.append(f"- reset: none from the owner on #{epic}")
    if resets.ignored:
        names = ", ".join(resets.ignored_logins) or "unknown"
        lines.append(f"- ignored reset tokens: {resets.ignored} from non-owner logins ({names})")
    return lines


def build_report(
    share: Share,
    trigger: dict[str, Any],
    closes: tuple[int, ...],
    resets: ResetScan,
    epic: int,
) -> str:
    """Render the report as markdown. Deterministic, no I/O."""
    state = "TRIPPED" if share.tripped else "not tripped"
    issues = ", ".join(f"#{n}" for n in closes) if closes else "none"
    lines = [
        f"### Agent share breaker (report only, epic #{epic}, AC-8)",
        f"- trailing 7 days: {_percent_text(share)}",
        f"- breaker over {THRESHOLD_PERCENT}%: {state}",
        f"- trigger issue #{trigger['number']}: {source_of(trigger) or 'unlabeled'}",
        f"- would close {len(closes)}: {issues}",
        *_reset_lines(resets, epic),
        "- enforcement: none. No issue was closed, labeled, or commented on.",
    ]
    return "\n".join(lines)


def _flatten(pages: object) -> list[dict[str, Any]]:
    if not isinstance(pages, list):
        raise GhError("unexpected API payload shape")
    if pages and isinstance(pages[0], list):
        return [item for page in pages for item in page]
    return cast("list[dict[str, Any]]", pages)


def _gh(args: list[str]) -> str:
    """Run gh with an argument list and no shell. Return stdout or raise GhError."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GhError(str(exc)) from exc
    if result.returncode != 0:
        joined = " ".join(f"{result.stderr} {result.stdout}".split())
        raise GhError(joined.replace("::", ": :")[:300])
    return result.stdout


def fetch_one(owner: str, repo: str, number: int) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(_gh(["api", f"repos/{owner}/{repo}/issues/{number}"])))


def fetch_window_issues(owner: str, repo: str, since: datetime) -> list[dict[str, Any]]:
    stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    endpoint = f"repos/{owner}/{repo}/issues?state=all&per_page=100&since={stamp}"
    return _flatten(json.loads(_gh(["api", "--paginate", "--slurp", endpoint])))


def fetch_epic_comments(owner: str, repo: str, epic: int) -> list[dict[str, Any]]:
    endpoint = f"repos/{owner}/{repo}/issues/{epic}/comments?per_page=100"
    return _flatten(json.loads(_gh(["api", "--paginate", "--slurp", endpoint])))


def run_report(owner: str, repo: str, number: int, epic: int) -> str:
    """Fetch inputs, compute, and return the report text. Read-only."""
    trigger = fetch_one(owner, repo, number)
    anchor = parse_time(trigger["created_at"])
    issues = [trigger, *fetch_window_issues(owner, repo, anchor - WINDOW)]
    share = compute_share(issues, anchor)
    resets = find_resets(fetch_epic_comments(owner, repo, epic), owner)
    closes = would_close(share, trigger)
    return build_report(share, trigger, closes, resets, epic)


def _valid_name(value: str) -> bool:
    return _NAME_PATTERN.fullmatch(value) is not None and value not in {".", ".."}


def write_summary(report: str) -> None:
    """Append the report to the job summary when the runner provides one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(report + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", type=int, required=True, help="Triggering issue number")
    parser.add_argument("--owner", required=True, help="Repository owner login")
    parser.add_argument("--repo", required=True, help="Repository name")
    parser.add_argument("--epic", type=int, default=DEFAULT_EPIC, help="Epic issue number")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.issue < 1 or args.epic < 1 or not _valid_name(args.owner) or not _valid_name(args.repo):
        print("Invalid --issue, --epic, --owner, or --repo", file=sys.stderr)
        return EXIT_CONFIG
    try:
        report = run_report(args.owner, args.repo, args.issue, args.epic)
        write_summary(report)
    except (GhError, OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        print(
            f"::error::Could not compute breaker report for #{args.issue}: {exc}", file=sys.stderr
        )
        return EXIT_EXTERNAL
    print(report)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
