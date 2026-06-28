#!/usr/bin/env python3
"""Police staleness deferrals in build/scripts/build_all.py against orphaning.

Motivation (issue #2770)
========================
build_all.py --check is a "commit all generator output" gate: every file a
generator owns must match what is committed, or --check fails. SkillForge is a
"block a broken skill" gate. When a generator mirrors an upstream-broken skill,
the two deadlock: the mirror cannot be committed clean, so --check cannot pass.

The historical workaround was an ad-hoc ``STALENESS_DEFERRALS`` constant in
build_all.py that exempted the broken mirror's path from the staleness diff.
That workaround had two structural defects:

1. No sanctioned path. The next person facing a new upstream-broken skill
   re-invented the same ad-hoc exemption from scratch, with no rules.
2. Orphaned-deferral failure. The exemption's only drop-trigger was a comment
   on issue #2755. After the skills were fixed (#2762), nobody removed the dead
   exemption. It sat hiding stale mirrors until #2780 caught it by hand.

This validator makes defect 2 impossible to leave behind. It scans build_all.py
for any deferral-style exemption, extracts the tracking issue each one cites,
and FAILS the gate if that issue is CLOSED. A closed tracking issue is the exact
signature of an orphan: the work that justified the deferral is done, so the
deferral must go and the now-valid mirror must be committed.

Sanctioned deferral protocol
============================
A staleness deferral is a narrow, temporary escape valve, not a config surface.
If a generator change touches a NEW upstream-broken skill and you genuinely
cannot commit the clean mirror:

1. Open a tracking issue for the upstream breakage. It MUST stay open until the
   skill is fixed and the mirror is regenerated clean.
2. Add a deferral entry in build_all.py whose value or adjacent comment cites
   that OPEN issue as ``#<number>`` and states the reason.
3. When the upstream skill is fixed, regenerate the mirror, commit it, remove
   the deferral, and close the tracking issue.

This validator auto-polices step 3: once the tracking issue closes, the gate
fails until the deferral is removed. You cannot orphan it.

Scope
=====
This is a pure scanner over build_all.py source text plus a per-issue ``gh``
state lookup. It does not import or run build_all.py, so it stays out of the
build orchestrator's network-free, snapshot-pure path. build_all.py has zero
deferrals today (the #2780 cleanup removed the last one), so this gate passes
trivially until someone adds one.

Exit codes (per ADR-035):
    0 - no orphaned deferrals (no deferrals at all, or all cite OPEN issues,
        or issue state could not be resolved and was kept with a warning)
    1 - one or more deferrals cite a CLOSED tracking issue (orphan)
    2 - config error (build_all.py missing)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

# Bounded timeout for every subprocess call (Release It! integration-point rule).
_GH_TIMEOUT_S = 30

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILD_ALL = _REPO_ROOT / "build" / "scripts" / "build_all.py"

# A module-level constant whose name carries deferral / exemption intent. This
# is the shape of the historical ``STALENESS_DEFERRALS`` workaround and any
# re-invention of it. Anchored at column 0 (MULTILINE ^) so a local variable
# inside a function does not trip the scan.
_DEFERRAL_NAME_RE = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9_]*"
    r"(?:DEFERRAL|DEFERRALS|EXEMPTION|EXEMPTIONS|"
    r"STALENESS_SKIP|SKIP_STALENESS|STALENESS_ALLOWLIST))"
    r"\s*[:=]",
    re.MULTILINE,
)

# An issue reference inside a deferral block: ``#1234`` or ``issue 1234``.
_ISSUE_REF_RE = re.compile(r"(?:#|issue\s+)(\d{1,7})", re.IGNORECASE)


class DeferralBlock:
    """One deferral-style constant and the issue numbers it cites."""

    def __init__(self, name: str, start: int, end: int, text: str) -> None:
        self.name = name
        self.start_line = start
        self.end_line = end
        self.text = text
        self.issues = sorted({int(m.group(1)) for m in _ISSUE_REF_RE.finditer(text)})


def _block_extent(source_lines: list[str], name_line_idx: int) -> int:
    """Return the exclusive end line index of a deferral block.

    A block runs from its declaration line until the next column-0,
    non-comment, non-blank line (the next top-level statement). This captures
    multi-line list/dict literals and the comments interleaved with them.
    """
    idx = name_line_idx + 1
    n = len(source_lines)
    while idx < n:
        line = source_lines[idx]
        stripped = line.strip()
        is_indented = line[:1] in (" ", "\t")
        is_comment_or_blank = stripped == "" or stripped.startswith("#")
        if not is_indented and not is_comment_or_blank:
            break
        idx += 1
    return idx


def find_deferral_blocks(source: str) -> list[DeferralBlock]:
    """Return every deferral-style exemption block found in ``source``."""
    lines = source.splitlines()
    blocks: list[DeferralBlock] = []
    for match in _DEFERRAL_NAME_RE.finditer(source):
        name = match.group("name")
        start_idx = source.count("\n", 0, match.start())
        end_idx = _block_extent(lines, start_idx)
        text = "\n".join(lines[start_idx:end_idx])
        blocks.append(DeferralBlock(name, start_idx + 1, end_idx, text))
    return blocks


def lookup_issue_state(
    issue: int,
    repo: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    """Return the GitHub state ("OPEN"/"CLOSED") for ``issue``, or None.

    None signals an unresolved state: gh missing, not authenticated, network
    down, or the issue not found. Callers treat None as "keep but warn", never
    a hard fail, so an offline run does not block on a transient lookup.
    """
    try:
        result = runner(
            ["gh", "issue", "view", str(issue), "--repo", repo, "--json", "state"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_GH_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    state = data.get("state")
    if not isinstance(state, str):
        return None
    return state.upper()


def evaluate_deferrals(
    blocks: list[DeferralBlock],
    repo: str,
    *,
    lookup: Callable[[int, str], str | None] = lookup_issue_state,
) -> tuple[list[str], list[str]]:
    """Classify deferrals into orphan failures and keep-with-warning notices.

    Returns ``(failures, warnings)``. ``failures`` are deferrals citing a
    CLOSED issue (orphans). ``warnings`` are deferrals whose issue state could
    not be resolved (offline / unknown) and deferrals citing no issue at all.
    """
    failures: list[str] = []
    warnings: list[str] = []
    for block in blocks:
        if not block.issues:
            warnings.append(
                f"{block.name} (build_all.py:{block.start_line}) cites no "
                f"tracking issue; a deferral must reference an OPEN issue and "
                f"a reason"
            )
            continue
        for issue in block.issues:
            state = lookup(issue, repo)
            if state == "CLOSED":
                failures.append(
                    f"deferral {block.name} (build_all.py:{block.start_line}) "
                    f"references closed issue #{issue}; remove the deferral and "
                    f"commit the now-valid mirror"
                )
            elif state is None:
                warnings.append(
                    f"deferral {block.name} (build_all.py:{block.start_line}) "
                    f"references issue #{issue} but its state could not be "
                    f"resolved (offline or not found); keeping it"
                )
    return failures, warnings


def validate_no_orphaned_build_deferrals(
    build_all_path: Path = _BUILD_ALL,
    repo: str = "rjmurillo/ai-agents",
    *,
    lookup: Callable[[int, str], str | None] = lookup_issue_state,
) -> bool:
    """Return True when no deferral in build_all.py is orphaned.

    Importable entry point for pre_pr.py. Prints failures and warnings to
    stderr. Raises FileNotFoundError when build_all.py is missing so the
    caller can map it to a config-error exit.
    """
    if not build_all_path.is_file():
        raise FileNotFoundError(f"build_all.py not found: {build_all_path}")

    source = build_all_path.read_text(encoding="utf-8")
    blocks = find_deferral_blocks(source)
    if not blocks:
        return True

    failures, warnings = evaluate_deferrals(blocks, repo, lookup=lookup)
    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    for failure in failures:
        print(f"ORPHANED-DEFERRAL: {failure}", file=sys.stderr)
    return not failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-all",
        type=Path,
        default=_BUILD_ALL,
        help="Path to build_all.py (default: repo build/scripts/build_all.py).",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=os.environ.get("GH_REPO", "rjmurillo/ai-agents"),
        help="owner/name for gh issue-state lookups.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ok = validate_no_orphaned_build_deferrals(args.build_all, args.repo)
    except FileNotFoundError as exc:
        print(f"CONFIG-ERROR: {exc}", file=sys.stderr)
        return 2
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
