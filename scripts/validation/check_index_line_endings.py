#!/usr/bin/env python3
"""Block index blobs whose line endings contradict their gitattributes.

A file declared `text ... eol=lf` is supposed to hold LF in the index. A blob
that holds CRLF anyway is not a cosmetic problem: with `core.autocrlf=input`
the clean filter rewrites CRLF to LF on read, so the checked-out copy never
matches its own blob. Git's stat cache hides that right after checkout, then
reports the file modified the moment anything touches it, and any merge that
touches the path aborts with "Your local changes to the following files would
be overwritten by merge" in a worktree nobody edited.

Two such blobs reached `main` and broke merges in every worktree until
`git add --renormalize` cleaned them. Neither the clean filter nor any local
hook ran on them, because both commits were created through the GraphQL
`createCommitOnBranch` API, which uploads file contents verbatim. That path
stays available and is documented as the workaround when a sandbox cannot run
lefthook, so nothing upstream of the index can be relied on to prevent a
repeat. This check reads the index itself, which is the one place the defect
is always visible.

Exit codes follow ADR-035: 0 clean, 1 violations found, 2 git unavailable.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# `git ls-files --eol` prefixes the index state with `i/`. `mixed` is included
# because a blob holding both endings is broken the same way a pure-CRLF one
# is; `none` means no line endings at all and cannot contradict anything.
_BAD_INDEX_STATES = frozenset({"i/crlf", "i/mixed"})

# Only these attribute values promise LF in the index. A path marked `-text`
# is exempt by declaration, and `eol=crlf` asks for CRLF on purpose, so
# neither is a contradiction.
_LF_ATTRIBUTES = ("eol=lf",)

REMEDIATION = "git add --renormalize <path>, then commit the result"


@dataclass(frozen=True)
class Violation:
    """One tracked path whose index blob contradicts its attributes."""

    path: str
    index_state: str
    attributes: str

    def render(self) -> str:
        return (
            f"[CRLF] {self.path}: index blob is {self.index_state} "
            f"but attributes say {self.attributes}"
        )


def _run_ls_files_eol(repo_root: Path) -> str:
    """Return `git ls-files --eol` output, or raise RuntimeError."""
    result = subprocess.run(
        ["git", "ls-files", "--eol"],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git ls-files --eol failed ({result.returncode}): "
            f"{(result.stderr or '').strip()}"
        )
    return result.stdout


def parse_violations(output: str) -> tuple[list[Violation], int]:
    """Parse `git ls-files --eol` output into violations and an examined count.

    Each row is `i/<state> w/<state> attr/<attrs><TAB><path>`. The attribute
    field can carry several space-separated values, so the path is split on the
    tab rather than on whitespace: a path containing spaces would otherwise be
    truncated and silently drop a real violation.
    """
    violations: list[Violation] = []
    examined = 0
    for line in output.splitlines():
        if "\t" not in line:
            continue
        head, path = line.split("\t", 1)
        fields = head.split()
        if len(fields) < 3:
            continue
        examined += 1
        index_state = fields[0]
        attributes = " ".join(fields[2:])
        if index_state not in _BAD_INDEX_STATES:
            continue
        if not any(token in attributes for token in _LF_ATTRIBUTES):
            continue
        violations.append(
            Violation(path=path, index_state=index_state, attributes=attributes)
        )
    return violations, examined


def check_repository(repo_root: Path) -> tuple[list[Violation], int]:
    """Return violations and the number of tracked files examined."""
    return parse_violations(_run_ls_files_eol(repo_root))


def _report(violations: list[Violation], examined: int) -> None:
    """Print each violation plus the exact renormalize command that fixes it."""
    for violation in violations:
        print(f"  {violation.render()}")
    if violations:
        print(f"index-line-endings: {len(violations)} blob(s) contradict gitattributes")
        print(f"  Fix: {REMEDIATION}")
        paths = " ".join(v.path for v in violations)
        print(f"  git add --renormalize {paths}")
    print(f"index-line-endings: {len(violations)} violation(s) in {examined} tracked files")


def validate_index_line_endings(repo_root: Path) -> bool:
    """Blocking pre-PR gate. Returns False when any blob contradicts its attrs."""
    try:
        violations, examined = check_repository(repo_root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] index line endings: {exc}", file=sys.stderr)
        return False
    _report(violations, examined)
    return not violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inspect (default: current directory)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    # Separate from validate_index_line_endings so a broken git invocation
    # exits 2 (config error) instead of 1 (violations found). Collapsing the
    # two would report "line endings are wrong" when git never ran.
    try:
        violations, examined = check_repository(repo_root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] index line endings: {exc}", file=sys.stderr)
        return 2

    _report(violations, examined)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
