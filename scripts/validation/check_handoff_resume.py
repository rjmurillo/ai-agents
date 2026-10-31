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
# CommonMark lets a numbered item or an ATX heading start after up to 3 spaces.
_INDENTED_DECISION_LINE = re.compile(
    r"^(?P<indent> {1,3})(?:(?P<number>\d+[.)])|(?P<heading>\#{3,6}))[ \t](?P<title>.*)$"
)
# A table data row is a decision. The header row (the one above the separator) and the
# separator row are not.
_TABLE_ROW = re.compile(r"^ {0,3}\|.*\|[ \t]*$")
_TABLE_SEPARATOR_CELL = re.compile(r"^:?-+:?$")
# The handoff template lists these as sibling fields of a decision. Under a numbered
# or heading decision they sit at the top level, so they belong to that decision.
_ATTRIBUTE_KEYS = frozenset({"alternatives considered", "provenance", "superseded by"})
_TOP_LEVEL_ATTRIBUTE = re.compile(r"^[-*+] (?P<key>[A-Za-z ]+):[ \t]*(?P<value>.*)$")
_SUB_BULLET = re.compile(r"^\s+[-*+] (?P<key>[A-Za-z ]+):[ \t]*(?P<value>.*)$")
_URL_REMOTE = re.compile(
    r"^[a-z][a-z0-9+.-]*://(?:[^@/\s]+@)?(?P<host>[^/:@\s]+)(?::\d+)?/(?P<path>\S+)$", re.IGNORECASE
)
_SCP_REMOTE = re.compile(r"^(?:[^@/\s]+@)?(?P<host>[^/:@\s]+):(?P<path>[^/\s]\S*)$")
NO_ORIGIN = "(no origin remote)"


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


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    if not _TABLE_ROW.match(line):
        return False
    cells = _table_cells(line)
    return bool(cells) and all(_TABLE_SEPARATOR_CELL.match(cell) for cell in cells)


def _table_decisions(
    lines: list[str], index: int, header: list[str]
) -> tuple[int, list[tuple[str, bool]]]:
    """Return ``(next index, decisions)`` for the data rows of a table.

    ``header`` holds the lower-cased header cells. A row is sourced when the table has a
    ``Provenance`` column and the row's cell there is not blank or a placeholder.
    """
    column = header.index("provenance") if "provenance" in header else None
    rows: list[tuple[str, bool]] = []
    while index < len(lines) and _TABLE_ROW.match(lines[index]):
        cells = _table_cells(lines[index])
        sourced = column is not None and column < len(cells) and not _is_missing(cells[column])
        rows.append((cells[0] if cells else "", sourced))
        index += 1
    return index, rows


def _unrecognized_content(body: str) -> str:
    """Return the first Decisions Made line that is not blank, a placeholder, or an empty table.

    A table header with its separator and no data rows is an empty table, like an empty section.
    """
    lines = body.splitlines()
    for index, line in enumerate(lines):
        text = line.strip()
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        empty_table_part = _is_table_separator(line) or _is_table_separator(next_line)
        if text and not empty_table_part and not _PLACEHOLDER.match(text) and not _is_none(text):
            return text
    return ""


def _match_decision(line: str, content_offset: int | None) -> tuple[str, bool, int | None] | None:
    """Return ``(title, block_form, content offset)`` when ``line`` starts a decision.

    ``content_offset`` is the indent at which a line nests under the list item above, or
    ``None`` when that decision is not a list item. A heading has no offset.
    """
    found = _DECISION_LINE.match(line)
    indent = 0
    if not found:
        found = _INDENTED_DECISION_LINE.match(line)
        indent = len(found.group("indent")) if found else 0
        if found and content_offset is not None and indent >= content_offset:
            return None  # nested under the list item above, not a new decision
    if not found:
        return None
    groups = found.groupdict()
    marker = groups.get("bullet") or groups.get("number")
    offset = indent + len(marker) + 1 if marker else None
    return found.group("title").strip(), not groups.get("bullet"), offset


def decisions_without_provenance(text: str) -> list[str]:
    """Return the decision titles that lack a non-empty ``Provenance:`` sub-bullet.

    A heading decision is never treated as a group over bullet decisions: a heading
    with no ``Provenance:`` of its own is reported, so no unsourced decision passes
    by hiding under a grouping heading. Give the heading a ``Provenance:`` line.

    Only unindented items are decisions. An indented item belongs to the decision
    above it: the handoff template's ``Alternatives considered: {list}`` is
    legitimately a nested list, and counting its entries as decisions would HOLD
    every handoff that lists two alternatives. A numbered item or heading indented by
    1 to 3 spaces is still a top-level item in CommonMark, so it counts, unless it is
    indented past the content offset of a list decision above it, which nests it.

    A table data row is a decision, sourced by a ``Provenance`` column alone: a
    ``Provenance:`` bullet after a table never sources its last row. A section with
    content but no recognized decision (a paragraph) is reported as one unsourced
    decision, so prose cannot skip the check.
    """
    body = _section(_strip_comments(text), "Decisions Made")
    if not _has_heading(text, "Decisions Made"):
        return [MISSING_DECISIONS]
    decisions: list[tuple[str, bool]] = []
    block_form = False
    after_table = False  # the last decision is a table row, sourced by its cell alone
    content_offset: int | None = None  # indent at which a line nests under the last list item
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if (
            _TABLE_ROW.match(line)
            and not _is_table_separator(line)
            and index < len(lines)
            and _is_table_separator(lines[index])
        ):
            header = [cell.lower() for cell in _table_cells(line)]
            index, rows = _table_decisions(lines, index + 1, header)
            decisions.extend(rows)
            block_form = True
            after_table = after_table or bool(rows)  # an empty table replaces no decision
            content_offset = None
            continue
        attribute = _TOP_LEVEL_ATTRIBUTE.match(line)
        key = attribute.group("key").strip().lower() if attribute else ""
        if block_form and attribute and key in _ATTRIBUTE_KEYS:
            # Under a numbered or heading decision, an unindented attribute bullet
            # (`- Provenance:`, `- Alternatives considered:`) belongs to that decision,
            # not to a new bullet decision. Only a non-empty Provenance sources it.
            if (
                decisions
                and not after_table
                and key == "provenance"
                and not _is_missing(attribute.group("value"))
            ):
                decisions[-1] = (decisions[-1][0], True)
            continue
        found = _match_decision(line, content_offset)
        if found:
            title, block_form, content_offset = found
            after_table = False
            decisions.append((title, False))
            continue
        sub = _SUB_BULLET.match(line)
        has_source = (
            sub
            and sub.group("key").strip().lower() == "provenance"
            and not _is_missing(sub.group("value"))
        )
        if decisions and has_source and not after_table:
            decisions[-1] = (decisions[-1][0], True)
    if not decisions:
        stray = _unrecognized_content(body)
        return [f"unrecognized decision form: {stray}"] if stray else []
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


def _owner_name(path: str) -> str | None:
    parts = [part for part in path.removesuffix("/").removesuffix(".git").split("/") if part]
    return f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else None


def _parse_remote(text: str) -> tuple[str | None, str] | None:
    """Return (host, owner/name) from a remote, or None when it is not a repository reference.

    Accepts https/ssh URLs, scp-style git@host:owner/name, host/owner/name, and the
    host-less owner/name shorthand (host is None). Anything else, including the
    no-origin sentinel, is rejected.
    """
    text = text.strip()
    if not text or any(char.isspace() for char in text):
        return None
    match = _URL_REMOTE.match(text) or _SCP_REMOTE.match(text)
    if match:
        owner_name = _owner_name(match.group("path"))
        return (match.group("host").lower(), owner_name) if owner_name else None
    parts = text.removesuffix("/").removesuffix(".git").split("/")
    if len(parts) == 2 and all(parts):
        return None, f"{parts[0]}/{parts[1]}"
    if len(parts) == 3 and all(parts) and "." in parts[0]:
        return parts[0].lower(), f"{parts[1]}/{parts[2]}"
    return None


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


def _live_remote(repo: Path) -> tuple[str | None, str] | None:
    try:
        return _parse_remote(_git(repo, "remote", "get-url", "origin"))
    except GitError:
        _git(repo, "rev-parse", "--git-dir")  # not a repository: raise as an external failure
        return None


def _format_remote(remote: tuple[str | None, str] | None) -> str:
    if remote is None:
        return NO_ORIGIN
    host, owner_name = remote
    return f"{host}/{owner_name}" if host else owner_name


def _check_remote(recorded_text: str, repo: Path, report: Report) -> None:
    recorded = _parse_remote(recorded_text)
    if recorded is None:
        report.hold(f"remote is not a repository URL or owner/name: {recorded_text.strip()}")
        return
    live = _live_remote(repo)
    recorded_host, recorded_name = recorded
    live_host, live_name = live if live else (None, "")
    host_differs = recorded_host is not None and recorded_host != live_host
    if live is None or host_differs or recorded_name.lower() != live_name.lower():
        recorded_label = _format_remote(recorded)
        report.hold(f"remote mismatch: recorded {recorded_label}, live {_format_remote(live)}")


def _check_worktree(recorded_text: str, live_tree: Path, report: Report) -> None:
    recorded = Path(recorded_text).expanduser()
    if not recorded.is_absolute():
        report.hold(f"worktree is not an absolute path: {recorded_text}")
        return
    _compare(report, "worktree", str(recorded.resolve()), str(live_tree))


def _check_live(record: dict[str, str], repo: Path, report: Report) -> None:
    _check_remote(record["Remote"], repo, report)
    _compare(report, "branch", record["Branch"], _git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    live_tree = Path(_git(repo, "rev-parse", "--show-toplevel")).resolve()
    _check_worktree(record["Worktree"], live_tree, report)
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
