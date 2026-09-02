#!/usr/bin/env python3
"""Fail when a tracked prescription tells a reader to create a worktree in a bad place.

`.claude/rules/universal.md` MUST NOT 6 states the binding rule verbatim:

    Worktrees MUST be external: a sibling of the checkout or
    `~/worktrees/`, never under the clone, never under `/tmp`.

Two destinations break it, and this repository has paid for both:

  * Under the system temp directory. `/tmp` is reclaimed without warning, and a
    worktree carries the only copy of its unpushed commits. `/tmp/wt_4003` took
    roughly two hours of merge resolution with it
    (`.serena/memories/git/git-worktree-tmp-not-durable.md`). Issue #5111 then
    recorded six of them filling a 16G tmpfs to 4.0K free, which failed agent
    transcript writes and a backgrounded push with ENOSPC while the wrapper
    reported exit 0.
  * Inside the checkout. 59 worktrees under `.claude/worktrees/` turned a 0.49s
    test into a 422s failure, because much of this repository's tooling walks
    the filesystem rather than asking git what is tracked
    (`.serena/memories/git/git-never-place-worktrees-inside-the-checkout.md`).
    Gitignoring the directory hides it from git, not from a directory walk.

Issue #5111 asked why a rule plus a memory plus a documented prior incident
still produced six violations. Nothing read the recipes. This checker does.

WHAT COUNTS AS A RECIPE. A line invoking `git worktree add` in a tracked file
under `SCANNED_PREFIXES`. The path argument is the first non-flag token after
`add`, with value-taking flags and their values consumed first.

WHAT IS NOT JUDGED, AND WHY EACH CASE IS SKIPPED. Guessing here produces
findings a reader cannot act on, and a checker that cries wolf gets suppressed
wholesale, so three cases return no verdict:

  * A shell expansion anywhere in the token (`${dir}`, `$HOME/x`, a backtick).
    Its value is set elsewhere and cannot be read from the line.
  * A token that is not path-shaped, meaning it holds no `/` and does not begin
    with `.`. `git worktree add --detach`, a CI checkout` in prose yields the
    token `a`, and nothing separates an English word from a bare directory
    name. The cost of that cutoff is a missed bare-name destination
    (`git worktree add scratch`); no tracked prescription uses that form.
  * A home reference (`~/worktrees/x`). Home is outside the checkout and is not
    a temp filesystem, so the recipe is already correct.

A placeholder SEGMENT is judged, not skipped: `./.worktrees/pr-{number}` and
`../wt-<slug>` each count their placeholder as one ordinary directory level,
which is enough to settle whether the path stays inside the checkout. That is
the difference that catches the real `pr-review` recipes.

WHAT IS EXCLUDED. Trees whose purpose is recording what already happened. A
retrospective quoting a `/tmp` recipe is evidence, and rewriting it to match
current policy would destroy the record of why the policy exists. This mirrors
the same carve-out in `scripts/validation/check_push_lock_paths.py`, whose
EXCLUDED_PREFIXES reads:

    EXCLUDED_PREFIXES = (
        ".agents/retrospective/",
        ".agents/audits/",
        ".agents/archive/",
    )

Stricter/looser/different than that checker: this one adds `.agents/memory/`
and `.agents/sessions/` (episode and session records are also history), and it
scans every tracked text file under its prefixes rather than fenced Markdown
blocks only, because a worktree recipe appears in shell scripts too.

EXIT CODES (ADR-035):
  0 - every resolvable recipe names an external destination (prints the counts)
  1 - at least one recipe names a temp-root or in-checkout destination
  2 - configuration or runtime error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RULE_CITATION = ".claude/rules/universal.md MUST NOT 6 (git worktrees MUST be external)"

SCANNED_PREFIXES = (
    ".agents/",
    ".claude/",
    ".github/",
    "docs/",
    "scripts/",
    "src/",
    "templates/",
)

EXCLUDED_PREFIXES = (
    ".agents/archive/",
    ".agents/audits/",
    ".agents/memory/",
    ".agents/qa/",
    ".agents/retrospective/",
    ".agents/sessions/",
    ".claude/worktrees/",
)

SCANNED_SUFFIXES = (".md", ".py", ".sh", ".ps1", ".yml", ".yaml", ".txt")

# A line opts out by carrying this token, for prose that must quote a bad
# recipe in order to prohibit it.
HISTORICAL_MARKER = "worktree-recipe-historical"

_WORKTREE_ADD = re.compile(r"\bgit\s+worktree\s+add\b(?P<rest>.*)")

# `git worktree add` flags that consume the following token as their value.
_VALUE_FLAGS = frozenset({"-b", "-B", "--reason", "--lock-reason"})

# A shell expansion makes the token's value unreadable from the line.
_EXPANSION = re.compile(r"[$`]")
# Path-shaped: holds a separator, or is explicitly relative to the cwd.
_PATH_SHAPED = re.compile(r"/|^\.")

_TEMP_PREFIXES = ("/tmp/", "/var/tmp/", "/private/tmp/", "/dev/shm/")
_TEMP_EXACT = frozenset({"/tmp", "/var/tmp", "/private/tmp", "/dev/shm"})

REASON_TEMP = "names a temp-filesystem path; a reclaim takes the only copy of unpushed work"
REASON_IN_CHECKOUT = (
    "resolves inside the checkout; filesystem-walking tooling then scans every nested copy"
)


@dataclass(frozen=True, slots=True)
class Violation:
    """One bad worktree destination, located for the reader."""

    path: str
    line_number: int
    destination: str
    reason: str

    def render(self) -> str:
        """One reportable line naming file, line, destination, and why."""
        return (
            f"{self.path}:{self.line_number}: "
            f"worktree destination {self.destination!r} {self.reason}"
        )


def extract_destination(rest: str) -> str | None:
    """Return the path argument of a `git worktree add`, or None when absent.

    ``rest`` is everything after ``add``. Value-taking flags consume the token
    after them, boolean flags consume nothing, and the first surviving token is
    the destination. ``git worktree add <path> <commit-ish>`` puts the commit
    after the path, so taking the first token is correct for both arities.
    """
    tokens = rest.replace('"', " ").replace("'", " ").split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _VALUE_FLAGS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def classify(destination: str) -> str | None:
    """Return the violation reason for ``destination``, or None when acceptable.

    Returns None for the three skipped cases in the module docstring, and for
    the two acceptable ones: an absolute path outside a temp root, and a
    relative path that climbs out of the checkout (`../wt-<slug>`).
    """
    if not destination or _EXPANSION.search(destination):
        return None
    if not _PATH_SHAPED.search(destination):
        return None
    if destination.startswith("~"):
        return None

    normalized = destination.rstrip("/") or "/"
    if normalized in _TEMP_EXACT or destination.startswith(_TEMP_PREFIXES):
        return REASON_TEMP
    if destination.startswith("/"):
        return None

    # Relative. Walk the segments; rising above the checkout root settles it as
    # external. Known miss: a path that rises and then descends back in by the
    # checkout's own name (`../ai-agents/.worktrees/x`) reads as external,
    # because the recipe's text does not carry that name and nothing else
    # separates it from an ordinary sibling. No tracked prescription uses it.
    depth = 0
    for segment in destination.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            depth -= 1
            if depth < 0:
                return None
            continue
        depth += 1
    return REASON_IN_CHECKOUT


def scan_text(path: str, text: str) -> list[Violation]:
    """Return every violation in one file's text."""
    violations: list[Violation] = []
    for offset, line in enumerate(text.splitlines()):
        if HISTORICAL_MARKER in line:
            continue
        match = _WORKTREE_ADD.search(line)
        if match is None:
            continue
        destination = extract_destination(match.group("rest"))
        if destination is None:
            continue
        reason = classify(destination)
        if reason is None:
            continue
        violations.append(
            Violation(
                path=path,
                line_number=offset + 1,
                destination=destination,
                reason=reason,
            )
        )
    return violations


def is_scanned(path: str) -> bool:
    """True when ``path`` is a prescriptive surface this checker judges."""
    if not path.startswith(SCANNED_PREFIXES):
        return False
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    return path.endswith(SCANNED_SUFFIXES)


def tracked_files(repo_root: Path) -> list[str]:
    """Return tracked paths from the index, so a staged file is checked.

    Reads ``git ls-files -z``: paths are not newline-safe (`ci-scripts.md`
    MUST 9), and the index rather than a directory walk keeps untracked scratch
    and nested worktree checkouts out of the inventory.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=repo_root,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [entry for entry in result.stdout.split("\0") if entry]


def check_repository(repo_root: Path) -> tuple[list[Violation], int]:
    """Scan every prescriptive surface. Returns (violations, files examined)."""
    violations: list[Violation] = []
    examined = 0
    for relative in tracked_files(repo_root):
        if not is_scanned(relative):
            continue
        full = repo_root / relative
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        examined += 1
        violations.extend(scan_text(relative, text))
    return violations, examined


def validate_worktree_recipes(repo_root: Path) -> bool:
    """Blocking pre-PR gate. Returns False when any prescription is bad.

    Blocking, unlike the temp-filesystem report in
    ``scripts/validation/check_tmp_worktrees.py``. The subject here is tracked
    repository content, which the author of the diff owns and can fix, so the
    verdict is actionable at the moment it fires.
    """
    try:
        violations, examined = check_repository(repo_root)
    except (OSError, RuntimeError) as exc:
        print(f"[FAIL] worktree recipes: {exc}", file=sys.stderr)
        return False

    for violation in violations:
        print(f"  {violation.render()}")
    if violations:
        print(f"worktree-recipes: {len(violations)} violation(s) against {RULE_CITATION}")
        print("  Point the recipe at a sibling of the checkout, for example ../wt-<slug>")
    print(f"worktree-recipes: {len(violations)} violation(s) in {examined} examined files")
    return not violations


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(
        description="Fail when a tracked prescription creates a worktree in a bad place.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root to scan (default: this script's repository).",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    if not (repo_root / ".git").exists():
        print(f"error: not a git repository: {repo_root}", file=sys.stderr)
        return 2

    return 0 if validate_worktree_recipes(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
