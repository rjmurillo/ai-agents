#!/usr/bin/env python3
"""Fail-closed resume check for a per-issue handoff file.

The orchestrator's Resume Check (templates/agents/orchestrator.shared.md,
"Resume Check (fail closed)") says to compare the recorded remote, branch,
worktree, and head SHA with the live repository before any state-changing
action. This script is the deterministic half of that check. It reads the
``## State Record`` block of ``.agents/templates/HANDOFF.md`` and compares the
live-state anchors with git.

What it decides:
  * every required State Record field is present and not a ``{placeholder}``
  * the timestamp parses as ISO 8601
  * every decision under ``## Decisions Made`` has a ``Provenance:`` line
  * recorded remote owner/name, branch, worktree, and head SHA equal the live
    repository

What it does not decide (the orchestrator still does):
  * whether the Next action is already done, reverted, or superseded. When the
    recorded head is an ancestor of the live head the output says how many
    commits sit ahead, so the caller can read them against the Next action.
  * whether a dirty working tree is caused by the Next action. The tree is
    never an input, so an uncommitted change is not a mismatch.

The check only reads. Running it twice on the same state gives the same
result and changes nothing, which is what makes a duplicate resume safe.

EXIT CODES (ADR-035):
  0 - every anchor matches and the record is complete (RESUME)
  1 - HOLD: mismatch, missing field, or missing provenance
  2 - configuration error: handoff file or repository path unusable
  3 - external failure: git is missing or a git command failed
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_HOLD = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

REQUIRED_FIELDS = (
    "Remote",
    "Branch",
    "Worktree",
    "Head SHA",
    "Timestamp",
    "Objective",
    "Risk tier",
    "Acceptance",
    "Phase",
    "Next action",
    "Validation run",
)
MIN_SHA_LENGTH = 7
_REPO_ENV = frozenset({"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"})
MISSING_DECISIONS = "section ## Decisions Made is absent"
DUPLICATE = "{conflicting duplicate}"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_PLACEHOLDER = re.compile(r"^\{.*\}$")
_FIELD_LINE = re.compile(r"^[-*+] \*\*(?P<key>[^*]+)\*\*:[ \t]*(?P<value>.*)$")
# A decision is a bullet, a numbered item (`1.` or `1)`), or a `###` to `######`
# heading. Counting only bullets let a numbered or heading decision skip the
# provenance check entirely (issue #6506).
_DECISION_LINE = re.compile(
    r"^(?:(?P<bullet>[-*+])|(?P<number>\d+[.)])|(?P<heading>\#{3,6}))[ \t](?P<title>.*)$"
)
# The handoff template lists these as sibling fields of a decision. Under a numbered
# or heading decision they sit at the top level, so they belong to that decision.
_ATTRIBUTE_KEYS = frozenset({"alternatives considered", "provenance", "superseded by"})
_TOP_LEVEL_ATTRIBUTE = re.compile(r"^[-*+] (?P<key>[A-Za-z ]+):[ \t]*(?P<value>.*)$")
_SUB_BULLET = re.compile(r"^\s+[-*+] (?P<key>[A-Za-z ]+):[ \t]*(?P<value>.*)$")
_REMOTE_URL = re.compile(r"[:/](?P<owner>[^/:]+)/(?P<name>[^/]+?)(?:\.git)?/?$")


class GitError(RuntimeError):
    """A git command failed or git is unavailable."""


@dataclass
class Report:
    """Collected HOLD reasons."""

    holds: list[str] = field(default_factory=list)

    def hold(self, message: str) -> None:
        self.holds.append(message)


def _strip_comments(text: str) -> str:
    return _COMMENT.sub("", text)


def _has_heading(text: str, heading: str) -> bool:
    return bool(re.search(rf"(?m)^## {re.escape(heading)}\s*$", _strip_comments(text)))


def _section(text: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\s*$(?P<body>.*?)(?=^## |\Z)", text)
    return match.group("body") if match else ""


def parse_state_record(text: str) -> dict[str, str]:
    """Return ``{field: value}`` from the State Record section, comments removed."""
    values: dict[str, str] = {}
    for line in _section(_strip_comments(text), "State Record").splitlines():
        match = _FIELD_LINE.match(line.rstrip())
        if match:
            key = match.group("key").strip()
            duplicated = key in values and values[key] != match.group("value").strip()
            values[key] = DUPLICATE if duplicated else match.group("value").strip()
    return values


def _is_missing(value: str | None) -> bool:
    return value is None or not value.strip() or bool(_PLACEHOLDER.match(value.strip()))


def decisions_without_provenance(text: str) -> list[str]:
    """Return the decision titles that lack a non-empty ``Provenance:`` sub-bullet.

    A heading decision is never treated as a group over bullet decisions: a heading
    with no ``Provenance:`` of its own is reported, so no unsourced decision passes
    by hiding under a grouping heading. Give the heading a ``Provenance:`` line.
    """
    body = _section(_strip_comments(text), "Decisions Made")
    if not _has_heading(text, "Decisions Made"):
        return [MISSING_DECISIONS]
    decisions: list[tuple[str, bool]] = []
    block_form = False
    for line in body.splitlines():
        attribute = _TOP_LEVEL_ATTRIBUTE.match(line)
        key = attribute.group("key").strip().lower() if attribute else ""
        if block_form and attribute and key in _ATTRIBUTE_KEYS:
            # Under a numbered or heading decision, an unindented attribute bullet
            # (`- Provenance:`, `- Alternatives considered:`) belongs to that decision,
            # not to a new bullet decision. Only a non-empty Provenance sources it.
            if decisions and key == "provenance" and not _is_missing(attribute.group("value")):
                decisions[-1] = (decisions[-1][0], True)
            continue
        decision = _DECISION_LINE.match(line)
        if decision:
            decisions.append((decision.group("title").strip(), False))
            block_form = decision.group("bullet") is None
            continue
        sub = _SUB_BULLET.match(line)
        has_source = (
            sub
            and sub.group("key").strip().lower() == "provenance"
            and not _is_missing(sub.group("value"))
        )
        if decisions and has_source:
            decisions[-1] = (decisions[-1][0], True)
    return [title for title, sourced in decisions if not sourced and not _is_none(title)]


def _is_none(title: str) -> bool:
    return title.lower().strip("*. ") in {"none", "n/a"}


def _clean_git_env() -> dict[str, str]:
    """Drop variables that make ``git -C`` read a different repository (hook context)."""
    return {k: v for k, v in os.environ.items() if k not in _REPO_ENV}


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
        )
    except OSError as exc:
        raise GitError(f"git unavailable: {exc}") from exc
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _remote_owner_name(url: str) -> str:
    match = _REMOTE_URL.search(url)
    return f"{match.group('owner')}/{match.group('name')}" if match else url


def _check_required(record: dict[str, str], report: Report) -> None:
    for name in REQUIRED_FIELDS:
        if _is_missing(record.get(name)):
            report.hold(f"missing field: {name}")


def _check_timestamp(record: dict[str, str], report: Report) -> None:
    value = record.get("Timestamp")
    if value is None or _is_missing(value):
        return
    try:
        datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        report.hold(f"timestamp is not ISO 8601: {value}")


def _compare(report: Report, name: str, recorded: str, live: str) -> None:
    if recorded != live:
        report.hold(f"{name} mismatch: recorded {recorded}, live {live}")


def _check_head(repo: Path, recorded: str, live: str, report: Report) -> None:
    recorded = recorded.strip().lower()
    if len(recorded) < MIN_SHA_LENGTH or not re.fullmatch(r"[0-9a-f]+", recorded):
        report.hold(f"head SHA is not a hex SHA of at least {MIN_SHA_LENGTH} chars: {recorded}")
        return
    if live.startswith(recorded):
        return
    report.hold(f"head SHA mismatch: recorded {recorded}, live {live[:12]}{_ahead(repo, recorded)}")


def _ahead(repo: Path, recorded: str) -> str:
    try:
        count = _git(repo, "rev-list", "--count", f"{recorded}..HEAD")
        _git(repo, "merge-base", "--is-ancestor", recorded, "HEAD")
    except GitError:
        return " (recorded head is not an ancestor of live head)"
    return f" (live head is {count} commit(s) ahead; read them against the Next action)"


def _live_remote(repo: Path) -> str:
    try:
        return _remote_owner_name(_git(repo, "remote", "get-url", "origin"))
    except GitError:
        _git(repo, "rev-parse", "--git-dir")  # not a repository: raise as an external failure
        return "(no origin remote)"


def _check_live(record: dict[str, str], repo: Path, report: Report) -> None:
    live_remote = _live_remote(repo)
    _compare(report, "remote", _remote_owner_name(record["Remote"]).lower(), live_remote.lower())
    _compare(report, "branch", record["Branch"], _git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    live_tree = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    recorded_tree = Path(record["Worktree"]).expanduser().resolve()
    _compare(report, "worktree", str(recorded_tree), str(live_tree))
    _check_head(repo, record["Head SHA"], _git(repo, "rev-parse", "HEAD"), report)


def check_handoff(handoff: Path, repo: Path) -> Report:
    """Run every check and return the Report. Raises GitError for git failures."""
    text = handoff.read_text(encoding="utf-8")
    record = parse_state_record(text)
    report = Report()
    _check_required(record, report)
    _check_timestamp(record, report)
    for title in decisions_without_provenance(text):
        report.hold(f"decision without provenance: {title}")
    anchors = ("Remote", "Branch", "Worktree", "Head SHA")
    if not any(_is_missing(record.get(name)) for name in anchors):
        _check_live(record, repo, report)
    return report


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("handoff", type=Path, help="per-issue handoff markdown file")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="path inside the live worktree to compare against (default: cwd)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.handoff.is_file():
        print(f"[ERROR] handoff file not found: {args.handoff}", file=sys.stderr)
        return EXIT_CONFIG
    if not args.repo.is_dir():
        print(f"[ERROR] repository path is not a directory: {args.repo}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        report = check_handoff(args.handoff, args.repo)
    except GitError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    except UnicodeDecodeError as exc:
        print(f"[HOLD] handoff is not valid UTF-8: {exc}")
        return EXIT_HOLD
    except (OSError, ValueError) as exc:
        print(f"[ERROR] cannot read handoff or resolve its paths: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if report.holds:
        for reason in report.holds:
            print(f"[HOLD] {reason}")
        print("[HOLD] Surface the contradiction. Do not mutate on a guess.")
        return EXIT_HOLD
    print("[RESUME] State Record is complete and matches the live repository.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
