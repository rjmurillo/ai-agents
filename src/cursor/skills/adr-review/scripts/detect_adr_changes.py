#!/usr/bin/env python3
# taste-lint: ignore complexity -- pre-existing debt, unlinted before the ADR-119 source classification
"""Detect ADR file changes (create, update, delete) for automatic skill triggering.

Monitors ADR file patterns in designated directories and detects changes
since the last check. Returns structured JSON output for skill orchestration.

Patterns monitored:
- .project-toolkit/architecture/ADR-*.md
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
from datetime import datetime, timezone
from pathlib import Path

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
# This file's own plugin lib wins when it holds the shared frontmatter parser,
# so a foreign or older plugin root in the environment cannot shadow it. The
# environment root is the fallback for a script copied outside its plugin.
_PLUGIN_ROOT = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_LIB_DIR = Path(__file__).resolve().parents[3] / "lib"
if _PLUGIN_ROOT and not os.path.isfile(_LIB_DIR / "hook_utilities" / "frontmatter_block.py"):
    _LIB_DIR = Path(_PLUGIN_ROOT) / "lib"

if not os.path.isdir(_LIB_DIR):
    raise RuntimeError(
        "Expected portability helper lib directory not found: "
        f"{_LIB_DIR}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
        "plugin root, or run from an ai-agents checkout."
    )
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from hook_utilities.frontmatter_block import (  # noqa: E402
    FrontmatterStatus,
    decode_frontmatter_yaml,
    split_frontmatter,
)

# PyYAML is optional. This script runs under a consumer's bare ``python3``
# (`.claude/rules/plugin-self-containment.md` MUST 4), where PyYAML is not
# installed. Without it every frontmatter parse reports "cannot parse", which
# every caller already treats as fail closed: the adr-review gate still fires.
try:
    import yaml

    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False

ADR_PATTERNS = (
    ".project-toolkit/architecture/ADR-*.md",
    "docs/adr/ADR-*.md",
    "docs/architecture/ADR-*.md",
    "docs/decisions/ADR-*.md",
    "architecture/decisions/ADR-*.md",
)

ADR_DIRECTORIES = (
    ".project-toolkit/architecture",
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


# Frontmatter keys whose value can change without altering the ADR's decision
# content, so a change confined to them does not need adr-review. Per ADR-073
# (.project-toolkit/architecture/ADR-073-adr-lifecycle-frontmatter.md:57,61), `status`,
# `supersedes`, and `superseded-by` are authoritative governance state: a
# hand-edit to `status: accepted` MUST still trip the gate so the author binds
# it to adr-review evidence. Those keys are therefore deliberately EXCLUDED.
# Only the mechanical implementation flag (flips true at first merged change)
# is exempt; that is the case #2845 was filed for.
_NON_DECISION_FRONTMATTER_KEYS = frozenset({"implemented"})


def _parse_frontmatter(content: str) -> dict[str, object] | None:
    """Parse the leading frontmatter block of ``content`` into a mapping.

    Uses ``split_frontmatter`` and ``decode_frontmatter_yaml`` from
    ``hook_utilities.frontmatter_block``, so the fence rule and the YAML load are the
    ones every other gate uses. Returns ``None`` when the block is absent,
    unterminated, malformed, not a mapping, or repeats a key at any mapping
    depth, so callers fail closed (the gate still fires). An empty block is
    ``{}``. Also returns ``None`` when PyYAML is not installed: no parse is
    possible.

    Duplicate keys are rejected, not resolved last-wins. A second ``status:``
    line would otherwise mask the first, and a guard a forger can evade with
    quotation marks (``"status": proposed``) is worse than none. The core
    detects duplicates in the parser, not by line prefix, so quoting and
    nesting do not hide them.
    """
    if not _HAVE_YAML:
        return None
    split = split_frontmatter(content)
    if not split.found:
        return None
    # From the physical opening line: the fence match absorbs whitespace-only lines.
    try:
        loaded = decode_frontmatter_yaml(content[split.open_end : split.raw_end], yaml)
    except yaml.YAMLError:
        return None
    if loaded is None:
        return {}
    return loaded if isinstance(loaded, dict) else None


def _only_non_decision_fields_changed(old_content: str, new_content: str) -> bool:
    """True when every frontmatter key that changed is a non-decision field.

    Takes the two full documents. Compares parsed field maps. A key that was
    added, removed, or whose value changed counts as "changed". The change is
    exempt only when all such keys are in :data:`_NON_DECISION_FRONTMATTER_KEYS`;
    any governance key change (for example ``status: proposed`` -> ``accepted``)
    makes this False so the adr-review gate still fires (ADR-073).

    Fails closed when either side has a duplicate key (at any mapping depth)
    or malformed frontmatter: a duplicated or unparseable governance key
    could otherwise mask a status change.
    """
    old_fields = _parse_frontmatter(old_content)
    new_fields = _parse_frontmatter(new_content)
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

    Uses ``hook_utilities.frontmatter_block.split_frontmatter``. Returns
    ``("", content)`` when no complete block is present.
    """
    split = split_frontmatter(content)
    if split.status is not FrontmatterStatus.VALID:
        return "", content
    return split.raw, split.body


STATUS_UNKNOWN = "unknown"


def _get_adr_status(file_path: Path) -> str:
    """Return the ADR's declared lifecycle status, or ``unknown``.

    Reads ONLY the leading ``---`` fenced YAML frontmatter block, parsed with
    :func:`yaml.safe_load`. ADR-073
    (.project-toolkit/architecture/ADR-073-adr-lifecycle-frontmatter.md:57) states the
    contract this function implements verbatim:

        The frontmatter `status` enum is authoritative for tooling. The prose
        `## Status` section remains for humans and may carry the nuance the
        enum cannot

    and its Consequences at line 132 mandate the parser: "Mitigated by mandating
    `yaml.safe_load` and validating frontmatter in CI."

    The declared enum, quoted verbatim from the canonical template block at
    ADR-073 line 48::

        status: proposed | accepted | rejected | deprecated | superseded   # enum, no prose

    Returns :data:`STATUS_UNKNOWN` when the record declares no status: file
    missing or unreadable, no complete frontmatter block, malformed or
    non-mapping frontmatter, no ``status`` key, or a non-scalar value (a YAML
    sequence or mapping, e.g. ``status:\n  - accepted``). ``unknown`` is a
    distinct sentinel; callers MUST NOT treat it as ``proposed``. Collapsing
    "declares nothing" into "declares proposed" is the fail-open shape
    catalogued in
    .project-toolkit/retrospective/2026-08-19-review-and-land-fleet-campaign-prs.md
    (issue #5189). Malformed YAML never raises: :func:`_parse_frontmatter`
    returns ``None`` on :class:`yaml.YAMLError` or a non-mapping document,
    both mapped to ``unknown`` here.

    Stricter/looser/different than canonical: ADR-073 defines the enum but
    Phase 1 leaves it unenforced (line 18), so this does not validate against
    it; it lowercases whatever scalar ``status`` carries. The non-scalar
    rejection mirrors ``check_adr_lifecycle.py._status_of()`` verbatim
    (``value is None or isinstance(value, (list, dict))``, :409-414):
    previously a non-scalar reached ``str(status).lower()`` and returned a
    repr like ``"['accepted']"`` instead of ``unknown`` (Copilot, PR #5209
    round-6).
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
    # A duplicate `status:` key parses to None here, so it is undeclared, not
    # last-wins: a record with `status: proposed` near the top and
    # `status: accepted` lower would otherwise read as accepted to PyYAML and
    # as proposed to anyone scanning the first lines.
    fields = _parse_frontmatter(content)
    if fields is None:
        return STATUS_UNKNOWN
    status = fields.get("status")
    if status is None or isinstance(status, (list, dict)):
        return STATUS_UNKNOWN
    return str(status).strip().lower()


def _is_frontmatter_only_change(file_path: str, since_commit: str, base_path: Path) -> bool:
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
    old_split = split_frontmatter(show.stdout)
    new_split = split_frontmatter(new_content)
    if not old_split.found or not new_split.found:
        return False
    # Compare from just past the closing fence line, so a blank line added
    # right after the fence counts as a body change.
    if show.stdout[old_split.fence_end :] != new_content[new_split.fence_end :]:
        return False
    return _only_non_decision_fields_changed(show.stdout, new_content)


_HELP_EPILOG = """\
examples:
  %(prog)s
  %(prog)s --since-commit abc1234

exit codes:
  0  success (changes detected or no changes found)
  1  not a git repository, or an unexpected error during detection
  2  a file or directory is missing
  3  git diff failed (including an unknown --since-commit) or another I/O failure
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect ADR file changes for automatic skill triggering.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    (base_path / ".project-toolkit").mkdir(exist_ok=True)

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
            deleted_details.append(
                {
                    "Path": file_path,
                    "ADRName": adr_name,
                    "Status": "deleted",
                    "Dependents": dependents,
                }
            )

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
            "Timestamp": datetime.now(timezone.utc).isoformat(),
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
