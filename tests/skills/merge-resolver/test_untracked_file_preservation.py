"""Guard the autofix surfaces against verbs that destroy untracked files.

Issue #4790. An operator-owned untracked file vanished during an autofix run.
The auto-generated PRD on that issue named `git checkout <branch>` in
`resolve_pr_conflicts.py` as the cause and marked it "CONFIRMED in code". Run
against real git, it is not: a plain checkout leaves an unrelated untracked
path alone, and where the path is tracked on the target branch git refuses the
switch ("would be overwritten by checkout ... Aborting") instead of deleting
it, which the caller's own `if r.returncode != 0: return result` then turns
into a clean abort.

So the surfaces are clean today and the original cause remains unexplained.
What this file buys is the other half: a future edit cannot quietly introduce a
verb that WOULD destroy operator work without failing here first.

Scope is deliberately narrow, because precision matters more than breadth:

- `git clean` removes untracked files. Banned.
- A stash that includes untracked files (`-u`, `--include-untracked`, `-a`,
  `--all`) moves them out of the working tree, where a later pop conflict can
  strand them. Banned.
- `git reset --hard` and `git checkout -- .` are NOT banned. Both are
  destructive to tracked modifications and neither removes an untracked file,
  so banning them here would assert something untrue about the failure mode.
- `git worktree remove --force` is NOT banned. Its only call sites target a
  path validated by `get_safe_worktree_path()` or gated on
  `has_uncommitted_changes` (which counts untracked files), never the
  operator's own checkout.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Surfaces that run git against the operator's working tree during an autofix.
_SURFACE_FILES = (
    Path(".claude/commands/pr-autofix.md"),
    Path("src/copilot-cli/skills/pr-autofix/SKILL.md"),
)
_SURFACE_DIRS = (Path(".claude/skills/merge-resolver"),)

# Three invocation shapes reach git in these surfaces, and a scanner that
# knows only the shell form is blind to the one the merge-resolver actually
# uses (`_run_git("checkout", branch_name)`), so all three are matched:
#   shell:      git clean -fd
#   helper:     _run_git("clean", "-fd")
#   argv list:  subprocess.run(["git", "clean", "-fd"])
_GIT_CLEAN = re.compile(
    r"""\bgit\s+clean\b"""
    r"""|_run_git\(\s*["']clean["']"""
    r"""|["']git["']\s*,\s*["']clean["']"""
)
_STASH_WITH_UNTRACKED = re.compile(
    r"""\bgit\s+stash\b[^\n]*?(?:--include-untracked|--all|\s-\w*[ua])"""
    r"""|_run_git\(\s*["']stash["'][^\n]*?(?:--include-untracked|--all|-\w*[ua])"""
    r"""|["']git["']\s*,\s*["']stash["'][^\n]*?(?:--include-untracked|--all|-\w*[ua])"""
)


def _surface_paths() -> list[Path]:
    paths = [_REPO_ROOT / rel for rel in _SURFACE_FILES]
    for rel in _SURFACE_DIRS:
        root = _REPO_ROOT / rel
        paths.extend(sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts))
        paths.extend(sorted(root.rglob("*.md")))
    return paths


def test_the_scanned_surface_set_is_not_empty() -> None:
    """A guard that scans nothing passes vacuously and proves nothing."""
    paths = _surface_paths()
    assert len(paths) >= 3, f"expected the autofix surfaces to be present, found {paths}"
    for path in paths:
        assert path.is_file(), f"declared surface is missing: {path}"


def test_no_autofix_surface_runs_git_clean() -> None:
    offenders = [
        f"{path.relative_to(_REPO_ROOT)}:{i}"
        for path in _surface_paths()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _GIT_CLEAN.search(line)
    ]
    assert not offenders, (
        "git clean removes operator-owned untracked files (issue #4790). "
        f"Found at: {offenders}"
    )


def test_no_autofix_surface_stashes_untracked_files() -> None:
    offenders = [
        f"{path.relative_to(_REPO_ROOT)}:{i}"
        for path in _surface_paths()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _STASH_WITH_UNTRACKED.search(line)
    ]
    assert not offenders, (
        "stashing untracked files moves operator work out of the tree, where a "
        f"pop conflict can strand it (issue #4790). Found at: {offenders}"
    )


@pytest.mark.parametrize(
    "line",
    [
        "    git clean -fd",
        "run: git clean -xfd .",
        "subprocess.run(['git', 'clean', '-f'])",
        '    r = _run_git("clean", "-fd")',
        '    subprocess.run(["git", "clean", "-xfd"], check=False)',
    ],
)
def test_the_clean_scanner_flags_a_planted_line(line: str) -> None:
    """Negative control: a rule that never fires proves nothing.

    The helper and argv-list rows matter most. The merge-resolver reaches git
    through `_run_git("checkout", branch_name)`, so a scanner that recognised
    only the shell form would miss the very shape this codebase writes.
    """
    assert _GIT_CLEAN.search(line), f"scanner missed a real offender: {line!r}"


@pytest.mark.parametrize(
    "line",
    [
        "git stash --include-untracked",
        "git stash push -u",
        "git stash --all",
        '_run_git("stash", "--include-untracked")',
        'subprocess.run(["git", "stash", "-u"])',
    ],
)
def test_the_stash_scanner_flags_a_planted_line(line: str) -> None:
    """Negative control for the stash rule."""
    assert _STASH_WITH_UNTRACKED.search(line), f"scanner missed a real offender: {line!r}"


@pytest.mark.parametrize(
    "line",
    [
        "git stash",
        "git stash pop",
        "git reset --hard HEAD",
        "git checkout -- .",
        '_run_git("checkout", branch_name)',
        '_run_git("merge", "--abort")',
    ],
)
def test_the_scanners_do_not_flag_verbs_that_spare_untracked_files(line: str) -> None:
    """Edge: neither rule may fire on a verb that leaves untracked files alone.

    Over-broad rules get suppressed, and a suppressed rule guards nothing.
    """
    assert not _GIT_CLEAN.search(line), f"clean scanner over-matched: {line!r}"
    assert not _STASH_WITH_UNTRACKED.search(line), f"stash scanner over-matched: {line!r}"
