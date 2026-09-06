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

import json
import subprocess
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

# Seconds. A wedged git in a throwaway repo should fail the test, not the job.
_GIT_TEST_TIMEOUT = 30


def _z(*records: object) -> str:
    """Build ``git worktree list --porcelain -z`` output.

    Each record is a path, or a ``(path, "bare")`` pair. The production parser
    reads NUL-terminated attributes precisely so a newline inside a worktree
    path stays data instead of splitting the record, so the fixtures have to
    speak the same format the real command emits under ``-z``.
    """
    parts: list[str] = []
    for record in records:
        if isinstance(record, tuple):
            path, marker = record
            parts.append(f"worktree {path}\0{marker}\0\0")
        else:
            parts.append(f"worktree {record}\0\0")
    return "".join(parts)


def _recording_fake(
    worktree_listing: str,
    calls: list[tuple[list[str], object, object, dict[str, str] | None]],
    listing_exit_code: int = 0,
    status_exit_codes: dict[str, int] | None = None,
    status_by_worktree: dict[str, str] | None = None,
) -> _SubprocessFake:
    """A ``_run_subprocess`` stand-in that records every call's argv.

    The sibling module's fake keys on ``args[:2]`` and ignores the rest of the
    argv, so dropping ``--untracked-files=all`` or the pathspec leaves its whole
    suite green while the gate stops detecting new memory tiers.
    """
    status_exit_codes = status_exit_codes or {}
    status_by_worktree = status_by_worktree or {}

    def _fake(
        args: list[str],
        cwd: object = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        calls.append((list(args), cwd, timeout, env))
        if args[:3] == ["git", "worktree", "list"]:
            return listing_exit_code, worktree_listing, ""
        if args[:2] == ["git", "status"]:
            return status_exit_codes.get(str(cwd), 0), status_by_worktree.get(str(cwd), ""), ""
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
    calls: list[tuple[list[str], object, object, dict[str, str] | None]] = []

    listing = _z(current.resolve(), sibling.resolve())
    fake = _recording_fake(listing, calls)
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    checker.build_scope_report(current)

    status_calls = [c for c in calls if c[0][:2] == ["git", "status"]]
    assert len(status_calls) == 1
    args, _cwd, timeout, _env = status_calls[0]
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

    listing = _z((bare.resolve(), "bare"), current.resolve())
    fake = _recording_fake(listing, [], status_exit_codes={str(bare.resolve()): 128})
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.unreadable_worktrees == 0
    assert report.other_worktrees_examined == 0
    assert report.findings == []


def test_parse_worktree_records_reads_the_bare_marker_per_record() -> None:
    porcelain = _z(("/repo/bare", "bare"), "/repo/wt")

    assert checker.parse_worktree_records(porcelain) == [("/repo/bare", True), ("/repo/wt", False)]


def test_parse_worktree_records_keeps_a_path_containing_a_newline_whole() -> None:
    """A line-based parser keeps only the first fragment of such a path, so the
    scan skips a real worktree and never reports the stray memory inside it.
    Under ``-z`` the newline is ordinary data."""
    porcelain = _z("/repo/we\nird", "/repo/plain")

    assert checker.parse_worktree_records(porcelain) == [
        ("/repo/we\nird", False),
        ("/repo/plain", False),
    ]


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

    listing = _z(current.resolve(), sibling.resolve())

    def _fake(
        args: list[str],
        cwd: object = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
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
        args: list[str],
        cwd: object = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
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
        args: list[str],
        cwd: object = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
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


def test_both_git_calls_run_with_ambient_git_variables_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A push from a linked worktree exports GIT_DIR into the pre-push hook, and
    this gate runs inside pre_pr.py which that hook runs. An exported GIT_DIR,
    GIT_WORK_TREE or GIT_INDEX_FILE outranks cwd=, so an unsanitized scan reads
    the pushing worktree rather than the sibling it was aimed at. Measured on
    git 2.43.0, with GIT_DIR and GIT_WORK_TREE both set every sibling reports
    empty, so the gate reports a scan it never performed."""
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    calls: list[tuple[list[str], object, object, dict[str, str] | None]] = []

    monkeypatch.setenv("GIT_DIR", "/somewhere/else/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/somewhere/else")
    monkeypatch.setenv("GIT_INDEX_FILE", "/somewhere/else/.git/index")
    monkeypatch.setenv("git_dir", "/lowercased/too/.git")

    fake = _recording_fake(_z(current.resolve(), sibling.resolve()), calls)
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    checker.build_scope_report(current)

    assert len(calls) == 2, "expected the worktree listing and one sibling status call"
    for args, _cwd, _timeout, env in calls:
        assert env is not None, f"{args[:3]} inherited the ambient environment"
        leaked = sorted(name for name in env if name.upper().startswith("GIT_"))
        assert leaked == [], f"{args[:3]} leaked {leaked}"
    assert any("PATH" in (env or {}) for *_rest, env in calls), (
        "stripping must be narrow: PATH and the config variables stay, since this "
        "scans real checkouts where a global safe.directory entry is load-bearing"
    )


def test_the_worktree_listing_is_requested_nul_delimited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without -z a newline inside a worktree path splits the record."""
    current = tmp_path / "current"
    current.mkdir()
    calls: list[tuple[list[str], object, object, dict[str, str] | None]] = []

    fake = _recording_fake(_z(current.resolve()), calls)
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    checker.build_scope_report(current)

    listing_calls = [c for c in calls if c[0][:3] == ["git", "worktree", "list"]]
    assert len(listing_calls) == 1
    assert "-z" in listing_calls[0][0]


# --- main() / CLI ------------------------------------------------------------


def _init_repo(path: Path) -> None:
    """Create a throwaway repo for the CLI tests, with timeouts so a wedged git
    fails this test instead of hanging the session until the job timeout."""
    subprocess.run(
        ["git", "init", "-q", str(path)], check=True, cwd=path, timeout=_GIT_TEST_TIMEOUT
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        check=True,
        cwd=path,
        timeout=_GIT_TEST_TIMEOUT,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], check=True, cwd=path, timeout=_GIT_TEST_TIMEOUT
    )


def test_main_exits_zero_on_a_real_single_worktree_repo(tmp_path: Path) -> None:
    """End-to-end with real git, hermetic under tmp_path: no linked worktrees,
    nothing under .serena/memories/, so nothing to find."""
    repo = tmp_path / "solo-repo"
    repo.mkdir()
    _init_repo(repo)

    exit_code = checker.main(["--repo-root", str(repo)])

    assert exit_code == 0


def test_main_exits_two_when_repo_root_does_not_exist(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    exit_code = checker.main(["--repo-root", str(missing)])

    assert exit_code == 2


def test_main_exits_one_and_prints_json_when_a_sibling_has_a_stray_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    listing = _z(current.resolve(), sibling.resolve())
    fake = _recording_fake(
        listing,
        [],
        status_by_worktree={str(sibling.resolve()): "?? .serena/memories/git/stray.md\n"},
    )
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    exit_code = checker.main(["--repo-root", str(current), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["relpath"] == ".serena/memories/git/stray.md"
