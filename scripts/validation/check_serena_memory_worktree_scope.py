#!/usr/bin/env python3
"""Detect a Serena memory file that landed in the wrong git worktree (issue #5061).

Issue #5061 reported that ``mcp__serena__write_memory``, called from a
subagent whose cwd was a linked git worktree, wrote its new memory file into
the MAIN checkout's ``.serena/memories/`` tree instead of the worktree's own.
The file arrived untracked in a checkout the calling agent never touched
directly, invisible to the agent's own branch and commits.

ROOT CAUSE, confirmed from upstream and this repo's own launch config
(issue #5061 comment, 2026-09-04): the Serena MCP server resolves its project
root once, at server startup, from ``--project`` (see ``.mcp.json``, which
passes ``${workspaceFolder:-.}``) or a later ``activate_project`` call. It is
never resolved per tool call. One server serves the whole session, subagents
included, so a worktree-scoped subagent has no server of its own to point
elsewhere; every ``write_memory`` call in that session lands under whichever
checkout was active when the server started. This is a defect in a
third-party MCP server (github.com/oraios/serena), not in this repository's
own code, and no value of this repo's own configuration changes it: neither
``--project <worktree>`` nor ``--project-from-cwd`` re-resolve after launch,
and calling ``activate_project`` from the subagent redirects the *whole
server's* root, corrupting the parent session's writes instead.

A ``PreToolUse`` hook, ``invoke_serena_memory_scope_guard.py``, blocked this
before it landed (PR #5152) by denying the write outright when the calling
worktree and the activated project root disagreed. ADR-097 retired every
tool-call hook, this one included, for an unrelated reason (Windows spawn
cost) and named the loss explicitly: "A Serena write can again land in the
wrong worktree's checkout ... Nothing replaces this." This module is the
replacement class of guard ADR-097 anticipated could exist outside the
tool-call-hook surface it retired: a Lefthook/pre-PR check that observes
committed *and untracked* state after the fact, rather than a hook that
intercepts the MCP call itself. It cannot prevent the stray write (only a
per-call fix in Serena's own activation model, or the retired hook, could do
that); it can make the stray file visible before it either gets lost as
clutter or gets accidentally committed to the wrong branch.

DETECTION. From the worktree running this check, list every other linked
worktree of the same repository (``git worktree list --porcelain``) and look
for untracked ``.serena/memories/**/*.md`` files in each one. An untracked
memory file sitting in a worktree nobody is actively drafting a memory in is
exactly the symptom issue #5061 described. The check never inspects its own
worktree's untracked memory files: those are ordinary in-progress work, not
evidence of a misdirected write.

ADVISORY, NOT BLOCKING, when wired into the pre-PR sequence.
``check_tmp_worktrees.validate_tmp_worktrees`` states the reasoning this
module follows verbatim: "The subject is machine state, not repository
state ... so a blocking verdict would refuse every push on that machine for
a condition the current diff did not create and the pushing agent may not
own." A sibling worktree with a stray memory file is exactly that class of
state: it was not created by the diff this check runs against, and the agent
running it does not own the sibling worktree. The standalone CLI below exits
1 on the same findings for a caller that wants the blocking form.

EXIT CODES (ADR-035):
  0 - no findings (prints the count of worktrees examined)
  1 - at least one untracked ``.serena/memories/**/*.md`` file in another
      worktree
  2 - configuration error (``--repo-root`` does not exist)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent

# checks_common imports subprocess_runner, which imports scripts.cli_exec
# (absolute), so the repo root must be importable even when this file runs as
# a plain script, not only via python -m or a caller that already set up
# scripts/validation on sys.path. Mirrors check_model_pins.py's block for the
# same reason (issue #3073).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))

from check_tmp_worktrees import parse_worktree_list  # noqa: E402
from checks_common import _run_subprocess  # noqa: E402

# Matches this repo's own glob for memory content, cited verbatim from
# lefthook.yml (the memory-token-update, memory-size, memory-index,
# memory-token-counts, memory-tier, memory-cross-reference, and
# memory-skill-format jobs all key on it): ".serena/memories/**/*.md"
_MEMORY_PATH_PREFIX = ".serena/memories/"
_MEMORY_FILE_SUFFIX = ".md"
_GIT_TIMEOUT_SECONDS = 10

ISSUE_CITATION = "issue #5061 (Serena write_memory can land in the wrong git worktree)"


@dataclass(frozen=True, slots=True)
class StrayMemoryFinding:
    """One untracked memory file found in a worktree other than the caller's."""

    worktree: str
    relpath: str


@dataclass
class ScopeReport:
    """What one scan found. ``other_worktrees_examined`` distinguishes a clean
    run (checked N sibling worktrees, found nothing) from a single-worktree
    repository (nothing to check at all).
    """

    current_worktree: str
    other_worktrees_examined: int = 0
    findings: list[StrayMemoryFinding] = field(default_factory=list)
    worktree_listing_failed: bool = False
    stale_worktree_entries: int = 0
    unreadable_worktrees: int = 0

    @property
    def has_findings(self) -> bool:
        """True when at least one sibling worktree carries a stray memory file."""
        return bool(self.findings)


def parse_stray_memory_files(porcelain: str) -> list[str]:
    """Return the untracked ``.serena/memories/**/*.md`` paths in ``git status`` output.

    Expects ``git status --porcelain --untracked-files=all -- .serena/memories``
    output. Only ``??`` (untracked) entries count: a *modified* tracked memory
    file is ordinary working-tree editing, not evidence of a misdirected write
    landing somewhere new. ``--untracked-files=all`` is required so a brand new
    ``.serena/memories/<tier>/`` directory is reported file by file rather than
    collapsed to one directory line, matching the file-level suffix filter
    below.

    Empty or whitespace-only input returns an empty list: a worktree with no
    stray memory files is the expected, common case, not an error.
    """
    findings: list[str] = []
    for line in porcelain.splitlines():
        if not line.startswith("?? "):
            continue
        path = line[len("?? ") :].strip()
        # git quotes a path containing unusual characters in double quotes;
        # memory filenames in this repo are ASCII kebab-case, so a bare strip
        # of a wrapping quote covers the realistic case without a full
        # C-style unquote implementation.
        path = path.strip('"')
        if path.startswith(_MEMORY_PATH_PREFIX) and path.endswith(_MEMORY_FILE_SUFFIX):
            findings.append(path)
    return findings


def _list_other_worktrees(repo_root: Path, current: str) -> tuple[list[str], bool]:
    """Return (sibling worktree paths, listing_failed).

    ``current`` is excluded by resolved-path comparison so the caller's own
    worktree is never scanned. Deduplicates in case ``git worktree list``
    ever reports the same admin path twice.
    """
    exit_code, stdout, _stderr = _run_subprocess(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_root,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if exit_code != 0:
        return [], True

    others: list[str] = []
    seen: set[str] = {current}
    for raw in parse_worktree_list(stdout):
        try:
            resolved = str(Path(raw).resolve())
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        others.append(resolved)
    return others, False


def _stray_files_in(worktree_path: str) -> tuple[list[str], bool]:
    """Return (stray memory relpaths, unreadable) for one sibling worktree.

    A git command failure is reported as unreadable, never raised: this is a
    read-only advisory scan, and one unreadable sibling must not stop the
    rest of the report (fail-open, mirroring
    ``check_tmp_worktrees._list_registered``).
    """
    exit_code, stdout, _stderr = _run_subprocess(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", ".serena/memories"],
        cwd=worktree_path,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if exit_code != 0:
        return [], True
    return parse_stray_memory_files(stdout), False


def build_scope_report(repo_root: Path) -> ScopeReport:
    """Scan every other worktree of ``repo_root``'s repository for stray memory files."""
    current = str(repo_root.resolve())
    report = ScopeReport(current_worktree=current)

    others, listing_failed = _list_other_worktrees(repo_root, current)
    report.worktree_listing_failed = listing_failed
    if listing_failed:
        return report

    for worktree in others:
        if not Path(worktree).is_dir():
            # Registered but gone (merged and removed, or not yet created on
            # this machine). Not a failure: skip silently, same as a
            # single-worktree repository skips nothing to check.
            report.stale_worktree_entries += 1
            continue

        report.other_worktrees_examined += 1
        stray, unreadable = _stray_files_in(worktree)
        if unreadable:
            report.unreadable_worktrees += 1
            continue
        for relpath in stray:
            report.findings.append(StrayMemoryFinding(worktree=worktree, relpath=relpath))

    return report


def format_report(report: ScopeReport) -> str:
    """Render the human-readable report. Always names the examined count."""
    lines: list[str] = []

    if report.worktree_listing_failed:
        return (
            "serena-memory-worktree-scope: git worktree list failed; "
            "nothing was examined"
        )

    for finding in report.findings:
        lines.append(f"  {finding.worktree}: {finding.relpath}")

    if report.findings:
        lines.insert(
            0,
            f"serena-memory-worktree-scope: {len(report.findings)} untracked memory "
            f"file(s) found in a sibling worktree, against {ISSUE_CITATION}:",
        )
        lines.append(
            "  Likely cause: Serena's MCP server resolved its project root to that "
            "worktree when this session's write_memory call landed there instead of "
            f"here ({report.current_worktree}). Verify by hand: move the file into "
            "the worktree that should own it, or delete it if it duplicates a memory "
            "already written correctly."
        )

    if report.unreadable_worktrees:
        lines.append(
            f"serena-memory-worktree-scope: {report.unreadable_worktrees} sibling "
            "worktree(s) could not be read and were skipped."
        )

    lines.append(
        f"serena-memory-worktree-scope: {len(report.findings)} finding(s) across "
        f"{report.other_worktrees_examined} sibling worktree(s) examined "
        f"({report.stale_worktree_entries} stale entr(y/ies) skipped)."
    )
    return "\n".join(lines)


def validate_serena_memory_worktree_scope(repo_root: Path) -> bool:
    """Advisory pre-PR gate. Prints findings and always returns True.

    Advisory for the same reason ``validate_tmp_worktrees`` is: the subject is
    another worktree's uncommitted state, not this diff's own repository
    state, so a blocking verdict would refuse this push for a condition it did
    not create and this agent does not own. The standalone CLI below exits 1
    on the same findings for a caller that wants the blocking form.
    """
    report = build_scope_report(repo_root)
    print(format_report(report))
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Report untracked Serena memory files sitting in a sibling git "
            "worktree (issue #5061)."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to scan from (default: this script's own repo root).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)

    repo_root = args.repo_root if args.repo_root is not None else _REPO_ROOT
    if not repo_root.is_dir():
        print(f"error: --repo-root is not a directory: {repo_root}", file=sys.stderr)
        return 2

    report = build_scope_report(repo_root)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report))
    return 1 if report.has_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
