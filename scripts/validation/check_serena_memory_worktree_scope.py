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
  2 - configuration or environment error: ``--repo-root`` does not exist, or
      ``git worktree list`` itself failed so nothing could be examined. A scan
      that could not look never reports 0: a scripted caller reads the exit
      code, not the text.
"""

from __future__ import annotations

import argparse
import json
import os
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


def _git_environment() -> dict[str, str]:
    """Environment for this scan's git calls, with every ambient ``GIT_*`` removed.

    ``git push`` from a linked worktree exports ``GIT_DIR`` into the pre-push
    hook, and this gate runs inside ``pre_pr.py``, which the pre-push hook runs.
    An exported ``GIT_DIR``, ``GIT_WORK_TREE`` or ``GIT_INDEX_FILE`` outranks
    ``cwd=``, so a sibling scan would read the pushing worktree rather than the
    sibling it was pointed at.

    Measured on git 2.43.0, a sibling holding a file the scan should see:

        clean env,   cwd=sibling            ' M .serena/memories/git/stray.md'
        GIT_DIR,     cwd=sibling            ' M .serena/memories/git/stray.md'
        GIT_DIR + GIT_WORK_TREE             ''

    The third row is the defect: every sibling reads clean, so the gate reports
    a scan it never performed. Issue #4914 is the same class in the count
    ratchets, and ``scripts/ci/count_ratchet.py`` records the same measurement.

    Mirrors the ``GIT_*`` half of the rule that file quotes verbatim, including
    its ``name.upper()`` so a lowercased ``git_dir`` folded by a
    case-insensitive platform is stripped too. ``HOME`` and the config
    variables are deliberately kept: this scans real checkouts, where a global
    ``safe.directory`` entry is load-bearing.
    """
    env = os.environ.copy()
    for name in tuple(env):
        if name.upper().startswith("GIT_"):
            env.pop(name)
    return env


def parse_worktree_records(porcelain: str) -> list[tuple[str, bool]]:
    """Return ``(path, is_bare)`` per record of ``git worktree list --porcelain -z``.

    ``-z`` is required rather than preferred. Without it git delimits attributes
    with newlines, so a worktree path that itself contains a newline is split
    across lines and a line-based parser keeps only the first fragment. The scan
    then skips a real worktree and never reports the stray memory inside it.
    Under ``-z`` every attribute is NUL-terminated and a record ends at an empty
    attribute, so a newline in a path is ordinary data.

    A bare repository is flagged rather than returned as scannable: it has no
    working tree, so ``git status`` there exits 128 and it can never hold a
    stray memory file. Counting it unreadable would print a permanent
    scan-failure line on the bare-clone-plus-worktrees layout this gate serves,
    which trains the reader to ignore the line that flags a real failure.

    ``check_tmp_worktrees.parse_worktree_list`` is deliberately left alone
    rather than widened: it is line-based, serves a different gate, and changing
    its contract to suit this one would put that gate's behavior in scope here.
    """
    records: list[tuple[str, bool]] = []
    path: str | None = None
    bare = False
    for attribute in porcelain.split("\0"):
        if attribute == "":
            if path is not None:
                records.append((path, bare))
            path, bare = None, False
            continue
        if attribute.startswith("worktree "):
            path = attribute[len("worktree ") :]
        elif attribute == "bare":
            bare = True
    if path is not None:
        records.append((path, bare))
    return records


def _list_other_worktrees(repo_root: Path, current: str) -> tuple[list[str], bool]:
    """Return (sibling worktree paths, listing_failed).

    ``current`` is excluded by resolved-path comparison so the caller's own
    worktree is never scanned. Deduplicates in case ``git worktree list``
    ever reports the same admin path twice.
    """
    try:
        exit_code, stdout, _stderr = _run_subprocess(
            ["git", "worktree", "list", "--porcelain", "-z"],
            cwd=repo_root,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_environment(),
        )
    except OSError:
        # ``_run_subprocess`` absorbs FileNotFoundError and TimeoutExpired but
        # lets every other OSError through, and ``pre_pr.run_validation`` turns
        # any exception into a FAIL. An advisory gate that fails the push is not
        # advisory, so a listing that cannot run reports itself failed instead.
        return [], True
    if exit_code != 0:
        return [], True

    others: list[str] = []
    seen: set[str] = {current}
    for raw, is_bare in parse_worktree_records(stdout):
        if is_bare:
            continue
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

    That promise covers two distinct failures. A git process that runs and exits
    non-zero returns through ``exit_code``. A failure BEFORE git starts raises:
    ``_run_subprocess`` catches only FileNotFoundError and TimeoutExpired, so a
    sibling directory that stats but cannot be entered (mode 600, or a locked
    Windows handle) raises PermissionError out of ``subprocess.run(cwd=...)``.
    ``pre_pr.run_validation`` converts any exception into a FAIL, which would
    make this advisory gate block the push. Both are caught here.

    ``--untracked-files=all`` is load-bearing, not cosmetic: without it git
    collapses a brand-new ``.serena/memories/<tier>/`` directory to a single
    directory line, which fails the ``.md`` suffix filter. A write into a tier
    the sibling's branch does not carry is precisely the issue #5061 symptom.
    """
    try:
        exit_code, stdout, _stderr = _run_subprocess(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", ".serena/memories"],
            cwd=worktree_path,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_environment(),
        )
    except OSError:
        return [], True
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

        stray, unreadable = _stray_files_in(worktree)
        if unreadable:
            # Counted as unreadable, NOT as examined. Collapsing the two would
            # let the summary line report a clean scan of a worktree nothing
            # could read, contradicting the "could not be read" line above it.
            # ``check_tmp_worktrees.scan_temp_root`` orders these the same way.
            report.unreadable_worktrees += 1
            continue

        report.other_worktrees_examined += 1
        for relpath in stray:
            report.findings.append(StrayMemoryFinding(worktree=worktree, relpath=relpath))

    return report


def format_report(report: ScopeReport) -> str:
    """Render the human-readable report. Always names the examined count."""
    lines: list[str] = []

    if report.worktree_listing_failed:
        return "serena-memory-worktree-scope: git worktree list failed; nothing was examined"

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
            "Report untracked Serena memory files sitting in a sibling git worktree (issue #5061)."
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

    if report.worktree_listing_failed:
        # Nothing was examined. Returning 0 here would hand a scripted caller a
        # machine-readable "clean" for a run that never looked.
        return 2
    return 1 if report.has_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
