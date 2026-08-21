#!/usr/bin/env python3
"""Detect ADR file changes (create, update, delete) for automatic skill triggering.

Monitors ADR file patterns in designated directories and detects changes
since the last check. Returns structured JSON output for skill orchestration.

Patterns monitored:
- .agents/architecture/ADR-*.md
- docs/adr/ADR-*.md
- docs/architecture/ADR-*.md
- docs/decisions/ADR-*.md
- architecture/decisions/ADR-*.md

Exit codes follow ADR-035:
    0 - Success (changes detected or no changes found)
    1 - Logic or unexpected error during detection
    2 - Config/user error (invalid commit SHA, missing file)
    3 - External error (I/O failure, git command failure)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ADR_PATTERNS = (
    ".agents/architecture/ADR-*.md",
    "docs/adr/ADR-*.md",
    "docs/architecture/ADR-*.md",
    "docs/decisions/ADR-*.md",
    "architecture/decisions/ADR-*.md",
)

ADR_DIRECTORIES = (
    ".agents/architecture",
    "docs/adr",
    "docs/architecture",
    "docs/decisions",
    "architecture/decisions",
)


def _get_dependent_adrs(adr_name: str, base_path: Path) -> list[str]:
    """Find ADRs that reference a given ADR."""
    dependents: list[str] = []
    for directory in ADR_DIRECTORIES:
        dir_path = base_path / directory
        if not dir_path.is_dir():
            continue
        for adr_file in dir_path.glob("ADR-*.md"):
            try:
                content = adr_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # UnicodeDecodeError subclasses ValueError, not OSError, so the
                # bare OSError arm never caught it and one record with a stray
                # byte aborted the whole dependent scan. Skipping matches the
                # OSError behaviour already chosen here: an unreadable record
                # cannot be searched for a reference, and this helper's job is
                # to list the records that DO reference the ADR.
                continue
            if adr_name in content:
                dependents.append(str(adr_file))
    return dependents


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


FRONTMATTER_DELIM = "---"

# Frontmatter keys whose value can change without altering the ADR's decision
# content, so a change confined to them does not need adr-review. Per ADR-073
# (.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md:57,61), `status`,
# `supersedes`, and `superseded-by` are authoritative governance state: a
# hand-edit to `status: accepted` MUST still trip the gate so the author binds
# it to adr-review evidence. Those keys are therefore deliberately EXCLUDED.
# Only the mechanical implementation flag (flips true at first merged change)
# is exempt; that is the case #2845 was filed for.
_NON_DECISION_FRONTMATTER_KEYS = frozenset({"implemented"})

# Top-level ``key:`` frontmatter line, used only to detect duplicate keys.
# Value parsing is delegated to PyYAML so block-style lists, multi-line
# values, and blank lines inside blocks are handled correctly.
_FRONTMATTER_FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")


def _parse_frontmatter(frontmatter: str) -> dict[str, object] | None:
    """Parse frontmatter into a key -> value mapping.

    Delegates to :func:`yaml.safe_load` so block-style lists, multi-line
    values, and blank lines inside block values are parsed the same way the
    real ADR tooling and CI parse them. Returns ``None`` on malformed input or
    a non-mapping document so callers can fail closed (still trip the gate).
    """
    try:
        loaded = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        return None
    return loaded


def _has_duplicate_top_level_keys(frontmatter: str) -> bool:
    """True when a top-level frontmatter key appears more than once.

    Duplicate keys are malformed YAML and can hide a governance change (a
    second ``status:`` line masking the first). PyYAML resolves duplicates
    last-wins without error, so this explicit check lets the exemption fail
    closed on them and the adr-review gate still fires.
    """
    seen: set[str] = set()
    for line in frontmatter.splitlines():
        if line and (line[0] == " " or line[0] == "\t"):
            continue
        match = _FRONTMATTER_FIELD_RE.match(line)
        if match:
            key = match.group(1)
            if key in seen:
                return True
            seen.add(key)
    return False


def _only_non_decision_fields_changed(old_frontmatter: str, new_frontmatter: str) -> bool:
    """True when every frontmatter key that changed is a non-decision field.

    Compares parsed field maps. A key that was added, removed, or whose value
    changed counts as "changed". The change is exempt only when all such keys
    are in :data:`_NON_DECISION_FRONTMATTER_KEYS`; any governance key change
    (for example ``status: proposed`` -> ``accepted``) makes this False so the
    adr-review gate still fires (ADR-073).

    Fails closed when either side has a duplicate top-level key or malformed
    frontmatter: a duplicated or unparseable governance key could otherwise
    mask a status change.
    """
    if _has_duplicate_top_level_keys(old_frontmatter) or _has_duplicate_top_level_keys(
        new_frontmatter
    ):
        return False
    old_fields = _parse_frontmatter(old_frontmatter)
    new_fields = _parse_frontmatter(new_frontmatter)
    if old_fields is None or new_fields is None:
        return False
    changed_keys = {
        key
        for key in old_fields.keys() | new_fields.keys()
        if old_fields.get(key) != new_fields.get(key)
    }
    if not changed_keys:
        return True
    return changed_keys <= _NON_DECISION_FRONTMATTER_KEYS


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split content into (frontmatter, body).

    Frontmatter is the YAML block delimited by a leading ``---`` line and a
    closing ``---`` line at the very start of the file. Returns
    ``("", content)`` when no complete frontmatter block is present.
    """
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return "", content
    for idx in range(1, len(lines)):
        if lines[idx].strip() == FRONTMATTER_DELIM:
            frontmatter = "".join(lines[1:idx])
            body = "".join(lines[idx + 1 :])
            return frontmatter, body
    return "", content


STATUS_UNKNOWN = "unknown"


def _get_adr_status(file_path: Path) -> str:
    """Return the ADR's declared lifecycle status, or ``unknown``.

    Reads ONLY the leading ``---`` fenced YAML frontmatter block, parsed with
    :func:`yaml.safe_load`. ADR-073
    (.agents/architecture/ADR-073-adr-lifecycle-frontmatter.md:57) states the
    contract this function implements verbatim:

        The frontmatter `status` enum is authoritative for tooling. The prose
        `## Status` section remains for humans and may carry the nuance the
        enum cannot

    and its Consequences at line 132 mandate the parser: "Mitigated by mandating
    `yaml.safe_load` and validating frontmatter in CI."

    The declared enum, quoted verbatim from the canonical template block at
    ADR-073 line 48::

        status: proposed | accepted | rejected | deprecated | superseded   # enum, no prose

    Returns :data:`STATUS_UNKNOWN` for every state in which the record declares
    no status: the file is missing or unreadable, there is no complete
    frontmatter block, the frontmatter is malformed or is not a YAML mapping, or
    the block carries no ``status`` key. ``unknown`` is a distinct sentinel and
    callers MUST NOT treat it as ``proposed``; only a record that literally
    declares ``status: proposed`` returns ``proposed``. Collapsing "declares
    nothing" into "declares proposed" is the fail-open shape catalogued in
    .agents/retrospective/2026-08-19-review-and-land-fleet-campaign-prs.md and is
    the bug this function was rewritten to fix (issue #5189).

    Malformed YAML never raises out of this function. Parsing is delegated to
    :func:`_parse_frontmatter`, which returns ``None`` on
    :class:`yaml.YAMLError` and on a non-mapping document; both map to
    ``unknown`` here, so a broken frontmatter block reads as an undeclared
    status rather than crashing the caller.

    Stricter/looser/different than canonical: ADR-073 defines the enum but
    Phase 1 leaves it unenforced ("optional, unenforced fields", line 18), so
    this function does NOT validate the value against the enum. It lowercases
    and strips whatever scalar the ``status`` key carries and returns it, which
    is looser than the deferred Phase 3 gate at ADR-073 line 159.
    """
    if not file_path.exists():
        return STATUS_UNKNOWN
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # UnicodeDecodeError subclasses ValueError, not OSError. Without it a
        # record with a stray byte raises past this handler instead of taking
        # the unknown-status path the caller is written to expect.
        return STATUS_UNKNOWN
    frontmatter, _body = _split_frontmatter(content)
    if not frontmatter:
        return STATUS_UNKNOWN
    if _has_duplicate_top_level_keys(frontmatter):
        # PyYAML resolves duplicates last-wins and reports nothing, so a record
        # carrying `status: proposed` near the top and `status: accepted` lower
        # in the same block parses as accepted while reading as proposed to
        # anyone scanning the first lines. This module already treats that as a
        # governance risk and fails its frontmatter-only exemption closed on it
        # (see _frontmatter_only_change); the status path was not wired to the
        # same helper, so the two disagreed about whether such a record is
        # readable at all. Undeclared, not last-wins.
        return STATUS_UNKNOWN
    fields = _parse_frontmatter(frontmatter)
    if fields is None:
        return STATUS_UNKNOWN
    status = fields.get("status")
    if status is None:
        return STATUS_UNKNOWN
    return str(status).strip().lower()


def _is_frontmatter_only_change(
    file_path: str, since_commit: str, base_path: Path
) -> bool:
    """Return True when a modified ADR changed only non-decision frontmatter.

    Compares the file body (content after the YAML frontmatter block) at
    ``since_commit`` against the current working-tree body, and requires every
    changed frontmatter key to be a non-decision field
    (:data:`_NON_DECISION_FRONTMATTER_KEYS`, currently the ADR-073
    ``implemented`` flag). Such a change is a metadata sync with no decision
    content and must not trigger the adr-review reminder (#2845).

    A change that touches the body, adds or removes the frontmatter block, or
    alters a governance frontmatter key (``status``, ``supersedes``,
    ``superseded-by``) is treated as substantive (returns False), so a hand-edit
    to ``status: accepted`` still trips the gate (ADR-073).
    """
    show = _run_git(["show", f"{since_commit}:{file_path}"], cwd=base_path)
    if show.returncode != 0:
        return False
    try:
        resolved_base = base_path.resolve()
        resolved_path = (resolved_base / file_path).resolve()
        if not resolved_path.is_relative_to(resolved_base):
            return False
        new_content = resolved_path.read_text(encoding="utf-8")
    except (OSError, RuntimeError, ValueError):
        return False
    old_frontmatter, old_body = _split_frontmatter(show.stdout)
    new_frontmatter, new_body = _split_frontmatter(new_content)
    if not old_frontmatter or not new_frontmatter:
        return False
    if old_body != new_body:
        return False
    return _only_non_decision_fields_changed(old_frontmatter, new_frontmatter)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect ADR file changes for automatic skill triggering.",
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--since-commit",
        default="HEAD~1",
        help="Git commit SHA to compare against (default: HEAD~1)",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked new ADR files in detection",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_path = Path(args.base_path).resolve()

    if not (base_path / ".git").exists():
        print(f"Error: Not a git repository: {base_path}", file=sys.stderr)
        return 1

    (base_path / ".agents").mkdir(exist_ok=True)

    original_dir = os.getcwd()
    try:
        os.chdir(base_path)

        created: list[str] = []
        modified: list[str] = []
        deleted: list[str] = []

        for pattern in ADR_PATTERNS:
            result = _run_git(
                ["diff", "--name-status", args.since_commit, "--", pattern],
                cwd=base_path,
            )
            if result.returncode != 0:
                print(
                    f"Error: git diff failed for pattern '{pattern}': {result.stderr.strip()}",
                    file=sys.stderr,
                )
                return 3

            for line in result.stdout.strip().splitlines():
                match = re.match(r"^([AMD])\s+(.+)$", line)
                if match:
                    status_char = match.group(1)
                    file_path = match.group(2)
                    if status_char == "A":
                        created.append(file_path)
                    elif status_char == "M":
                        modified.append(file_path)
                    elif status_char == "D":
                        deleted.append(file_path)

        if args.include_untracked:
            for directory in ADR_DIRECTORIES:
                dir_path = base_path / directory
                if not dir_path.is_dir():
                    continue
                result = _run_git(
                    ["ls-files", "--others", "--exclude-standard", "--", f"{directory}/ADR-*.md"],
                    cwd=base_path,
                )
                if result.returncode != 0:
                    print(
                        f"Warning: git ls-files failed for '{directory}': {result.stderr.strip()}",
                        file=sys.stderr,
                    )
                    continue
                for line in result.stdout.strip().splitlines():
                    if line:
                        created.append(line)

        created = sorted(set(created))
        deleted = sorted(set(deleted))

        # Partition modified ADRs: frontmatter-only edits (for example an
        # ADR-073 lifecycle-flag flip) are metadata syncs with no decision
        # content and must not trigger the adr-review reminder (#2845).
        substantive_modified: list[str] = []
        frontmatter_only_modified: list[str] = []
        for file_path in sorted(set(modified)):
            if _is_frontmatter_only_change(file_path, args.since_commit, base_path):
                frontmatter_only_modified.append(file_path)
            else:
                substantive_modified.append(file_path)

        recommended_action = "none"
        if created or substantive_modified:
            recommended_action = "review"
        elif deleted:
            recommended_action = "archive"

        deleted_details = []
        for file_path in deleted:
            adr_name = Path(file_path).stem
            dependents = _get_dependent_adrs(adr_name, base_path)
            deleted_details.append({
                "Path": file_path,
                "ADRName": adr_name,
                "Status": "deleted",
                "Dependents": dependents,
            })

        result_obj = {
            "Created": created,
            "Modified": substantive_modified,
            "ModifiedFrontmatterOnly": frontmatter_only_modified,
            "Deleted": deleted,
            "DeletedDetails": deleted_details,
            # Frontmatter-only metadata edits are reported separately and do not
            # count as actionable ADR changes for adr-review triggering.
            "HasChanges": len(created) + len(substantive_modified) + len(deleted) > 0,
            "RecommendedAction": recommended_action,
            "Timestamp": datetime.now(UTC).isoformat(),
            "SinceCommit": args.since_commit,
        }

        print(json.dumps(result_obj, indent=2))
        return 0

    except FileNotFoundError as exc:
        print(f"Error: File or directory not found: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: I/O failure: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Error detecting ADR changes: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_dir)


if __name__ == "__main__":
    raise SystemExit(main())
