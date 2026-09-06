"""Failure modes of the Serena memory worktree-scope gate (issue #5061).

Split from ``test_check_serena_memory_worktree_scope.py`` to keep both files
under the 500-line taste ceiling. Everything here came out of an adversarial
review of the gate's first commit, and each test below fails against that
commit unless its docstring says otherwise.

Covers the cases where the scan cannot run rather than the cases where it
finds something: git raising before it starts, a bare repository that has no
working tree to scan, the argv flags the detection silently depends on, and
the exit code of a run that examined nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Same import bootstrap as the sibling test module: prepend scripts/validation
# to sys.path and import by bare name. Never restored.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_serena_memory_worktree_scope as checker

_SubprocessFake = Callable[..., tuple[int, str, str]]


def _recording_fake(
    worktree_listing: str,
    calls: list[tuple[list[str], object, object]],
    listing_exit_code: int = 0,
    status_exit_codes: dict[str, int] | None = None,
) -> _SubprocessFake:
    """A ``_run_subprocess`` stand-in that records every call's argv.

    The sibling module's fake keys on ``args[:2]`` and ignores the rest of the
    argv, so dropping ``--untracked-files=all`` or the pathspec leaves its whole
    suite green while the gate stops detecting new memory tiers.
    """
    status_exit_codes = status_exit_codes or {}

    def _fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        calls.append((list(args), cwd, timeout))
        if args[:3] == ["git", "worktree", "list"]:
            return listing_exit_code, worktree_listing, ""
        if args[:2] == ["git", "status"]:
            return status_exit_codes.get(str(cwd), 0), "", ""
        raise AssertionError(f"unexpected subprocess call: {args}")

    return _fake


def test_the_status_call_asks_for_all_untracked_files_under_the_memories_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--untracked-files=all`` and the pathspec are load-bearing, so pin them.

    Without the flag git collapses a brand-new ``.serena/memories/<tier>/``
    directory to one directory line, which fails the ``.md`` suffix filter, and
    a write into a tier the sibling's branch does not carry is exactly the
    issue #5061 symptom. Every other test parses the fake's output and so stays
    green when the flag is dropped.
    """
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    calls: list[tuple[list[str], object, object]] = []

    listing = f"worktree {current.resolve()}\nworktree {sibling.resolve()}\n"
    fake = _recording_fake(listing, calls)
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    checker.build_scope_report(current)

    status_calls = [c for c in calls if c[0][:2] == ["git", "status"]]
    assert len(status_calls) == 1
    args, _cwd, timeout = status_calls[0]
    assert "--untracked-files=all" in args
    assert "--porcelain" in args
    assert args[-2:] == ["--", ".serena/memories"]
    assert timeout == checker._GIT_TIMEOUT_SECONDS


def test_a_bare_repository_is_skipped_rather_than_reported_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare repo has no working tree, so ``git status`` there exits 128.

    Reporting it "could not be read" on every run of a bare-clone-plus-worktrees
    layout trains the reader to ignore the line that flags a real scan failure.
    """
    current = tmp_path / "current"
    current.mkdir()
    bare = tmp_path / "bare"
    bare.mkdir()

    listing = (
        f"worktree {bare.resolve()}\nbare\n\nworktree {current.resolve()}\nbranch refs/heads/main\n"
    )
    fake = _recording_fake(listing, [], status_exit_codes={str(bare.resolve()): 128})
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.unreadable_worktrees == 0
    assert report.other_worktrees_examined == 0
    assert report.findings == []


def test_bare_worktree_paths_reads_the_marker_per_block() -> None:
    porcelain = "worktree /repo/bare\nbare\n\nworktree /repo/wt\nbranch refs/heads/x\n\n"

    assert checker._bare_worktree_paths(porcelain) == {"/repo/bare"}


def test_an_unenterable_sibling_is_unreadable_rather_than_an_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory that stats but cannot be entered raises PermissionError out of
    ``subprocess.run(cwd=...)``. ``_run_subprocess`` catches only
    FileNotFoundError and TimeoutExpired, and ``pre_pr.run_validation`` turns any
    exception into a FAIL, so an uncaught raise makes this advisory gate block
    the push."""
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    sibling_key = str(sibling.resolve())

    listing = f"worktree {current.resolve()}\nworktree {sibling.resolve()}\n"

    def _fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["git", "worktree", "list"]:
            return 0, listing, ""
        if str(cwd) == sibling_key:
            raise PermissionError(13, "Permission denied")
        return 0, "", ""

    monkeypatch.setattr(checker, "_run_subprocess", _fake)

    report = checker.build_scope_report(current)

    assert report.unreadable_worktrees == 1
    assert report.other_worktrees_examined == 0
    assert report.findings == []


def test_an_unrunnable_worktree_listing_is_reported_rather_than_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(checker, "_run_subprocess", _fake)

    report = checker.build_scope_report(tmp_path)

    assert report.worktree_listing_failed is True
    assert report.findings == []


def test_the_advisory_gate_still_returns_true_when_the_scan_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of finding 1: advisory must survive an unrunnable scan."""

    def _fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(checker, "_run_subprocess", _fake)

    assert checker.validate_serena_memory_worktree_scope(tmp_path) is True


def test_main_exits_two_when_the_listing_failed_so_nothing_was_examined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 0 here would hand a scripted caller a clean verdict from a run that
    never looked at anything."""
    fake = _recording_fake("", [], listing_exit_code=128)
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    assert checker.main(["--repo-root", str(tmp_path)]) == 2


def test_an_adjacent_prefix_directory_is_not_reported() -> None:
    """``.serena/memories-old/`` must not match ``.serena/memories/``.

    The trailing slash in the prefix is what stops it. Nothing else pins that,
    so removing the slash otherwise leaves the suite green.
    """
    porcelain = (
        "?? .serena/memories-old/decoy.md\n"
        "?? .serena/memoriesX/decoy.md\n"
        "?? .serena/memories/real.md\n"
    )

    assert checker.parse_stray_memory_files(porcelain) == [".serena/memories/real.md"]
