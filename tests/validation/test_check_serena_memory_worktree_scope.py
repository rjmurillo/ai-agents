"""Tests for the Serena memory worktree-scope advisory gate (issue #5061).

Coverage:

- positive: an untracked ``.serena/memories/**/*.md`` file in a sibling
  worktree is parsed, found, and reported.
- negative: a modified tracked memory file, a non-markdown untracked file, an
  untracked file outside ``.serena/memories/``, and the CALLING worktree's own
  untracked memory files are never reported (no over-fire).
- edge: blank input, a quoted path, a single-worktree repository, a stale
  (registered but deleted) sibling worktree, and a git command failure on
  either the listing or one sibling's status call.

Isolation: the git-status and git-worktree-list boundary is mocked
(``checker._run_subprocess``) for the unit-level tests, and the ``main()``
tests that exercise real git use only directories under ``tmp_path``.

One test is deliberately NOT hermetic.
``test_the_sequence_runs_the_gate_and_it_stays_advisory_on_the_real_tree``
drives the real pre-PR sequence against this repository, so it runs real
``git status`` in this machine's sibling worktrees. That is the point of the
test: it proves the gate stays advisory on a real tree. It is read-only and
writes nothing, but calling it hermetic would be false.

Nothing here writes this repository's own ``.serena/memories/`` tree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way pre_pr_sequence does (see that test file's header): prepend
# scripts/validation to sys.path and import by bare name. Never restored.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_serena_memory_worktree_scope as checker
import pre_pr_sequence

GATE_NAME = "Serena Memory Worktree Scope (advisory)"

_SubprocessFake = Callable[..., tuple[int, str, str]]


# --- parse_stray_memory_files ---------------------------------------------


def test_an_untracked_memory_markdown_file_is_reported() -> None:
    porcelain = "?? .serena/memories/git/foo.md\n"

    assert checker.parse_stray_memory_files(porcelain) == [".serena/memories/git/foo.md"]


def test_a_modified_tracked_memory_file_is_not_reported() -> None:
    """Only ``??`` (untracked) counts; a normal edit is not a stray write."""
    porcelain = " M .serena/memories/git/foo.md\n"

    assert checker.parse_stray_memory_files(porcelain) == []


def test_an_untracked_non_markdown_file_is_not_reported() -> None:
    porcelain = "?? .serena/memories/cache/tmp.bin\n"

    assert checker.parse_stray_memory_files(porcelain) == []


def test_an_untracked_file_outside_the_memories_prefix_is_not_reported() -> None:
    porcelain = "?? scratch/foo.md\n"

    assert checker.parse_stray_memory_files(porcelain) == []


@pytest.mark.parametrize("porcelain", ["", "   ", "\n\n"])
def test_blank_input_reports_nothing(porcelain: str) -> None:
    assert checker.parse_stray_memory_files(porcelain) == []


def test_a_git_quoted_path_is_still_detected_though_its_escapes_survive() -> None:
    """Git wraps a path in double quotes only when it holds a character needing
    an escape, so it C-escapes the same path. ``.strip('"')`` removes the
    wrapper but not the escapes, so the reported name is mangled while the file
    is still DETECTED, which is what an advisory report needs. A space alone
    does not trigger quoting, so the old fixture asserted on input git never
    emits.
    """
    porcelain = '?? ".serena/memories/git/caf\\303\\251.md"\n'

    found = checker.parse_stray_memory_files(porcelain)

    assert len(found) == 1
    assert found[0].startswith(".serena/memories/")
    assert found[0].endswith(".md")
    assert '"' not in found[0]


def test_multiple_lines_are_filtered_independently() -> None:
    porcelain = (
        "?? .serena/memories/git/stray.md\n"
        " M .serena/memories/git/tracked.md\n"
        "?? .serena/memories/cache/tmp.bin\n"
        "?? other/path/note.md\n"
    )

    assert checker.parse_stray_memory_files(porcelain) == [".serena/memories/git/stray.md"]


# --- build_scope_report ----------------------------------------------------


def _make_fake_run_subprocess(
    worktree_listing: str,
    status_by_worktree: dict[str, str],
    listing_exit_code: int = 0,
    status_exit_codes: dict[str, int] | None = None,
    record: list[tuple[list[str], object, object]] | None = None,
) -> _SubprocessFake:
    """Build a ``_run_subprocess`` stand-in keyed on the git subcommand and cwd.

    ``record``, when given, receives ``(args, cwd, timeout)`` for every call, so
    a test can assert on the argv rather than only on the parsed result. Without
    that, dropping ``--untracked-files=all`` or the pathspec leaves every test
    green while the gate silently stops detecting new memory tiers.
    """
    status_exit_codes = status_exit_codes or {}

    def _fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        if record is not None:
            record.append((list(args), cwd, timeout))
        if args[:3] == ["git", "worktree", "list"]:
            return listing_exit_code, worktree_listing, ""
        if args[:2] == ["git", "status"]:
            key = str(cwd)
            exit_code = status_exit_codes.get(key, 0)
            return exit_code, status_by_worktree.get(key, ""), ""
        raise AssertionError(f"unexpected subprocess call: {args}")

    return _fake


def test_a_stray_file_in_a_sibling_worktree_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    sibling_key = str(sibling.resolve())

    listing = f"worktree {current.resolve()}\nworktree {sibling.resolve()}\n"
    fake = _make_fake_run_subprocess(listing, {sibling_key: "?? .serena/memories/git/stray.md\n"})
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.has_findings is True
    assert report.findings == [
        checker.StrayMemoryFinding(worktree=sibling_key, relpath=".serena/memories/git/stray.md")
    ]
    assert report.other_worktrees_examined == 1


def test_the_current_worktrees_own_untracked_memory_file_is_never_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No over-fire: the caller's own in-progress memory drafts are not a finding.

    ``git status`` is never even invoked against the current worktree's own
    path: the fake raises if it is, so this also proves the exclusion happens
    before any status call, not merely that its result is discarded.
    """
    current = tmp_path / "current"
    current.mkdir()
    current_key = str(current.resolve())

    listing = f"worktree {current.resolve()}\n"

    def fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["git", "worktree", "list"]:
            return 0, listing, ""
        raise AssertionError(f"git status must not be called against the current worktree: {cwd}")

    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.has_findings is False
    assert report.other_worktrees_examined == 0
    assert current_key == str(Path(report.current_worktree))


def test_no_findings_when_every_sibling_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()

    listing = f"worktree {current.resolve()}\nworktree {sibling.resolve()}\n"
    fake = _make_fake_run_subprocess(listing, {str(sibling.resolve()): ""})
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.has_findings is False
    assert report.other_worktrees_examined == 1
    assert report.findings == []


def test_a_single_worktree_repository_examines_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current"
    current.mkdir()
    listing = f"worktree {current.resolve()}\n"
    fake = _make_fake_run_subprocess(listing, {})
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.other_worktrees_examined == 0
    assert report.has_findings is False


def test_a_stale_registered_worktree_is_skipped_without_a_status_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree git still lists but whose directory is gone is not a failure."""
    current = tmp_path / "current"
    current.mkdir()
    gone = tmp_path / "gone"  # never created on disk

    listing = f"worktree {current.resolve()}\nworktree {gone}\n"

    def fake(
        args: list[str], cwd: object = None, timeout: int | None = None
    ) -> tuple[int, str, str]:
        if args[:3] == ["git", "worktree", "list"]:
            return 0, listing, ""
        raise AssertionError(f"git status must not be called for a stale worktree: {cwd}")

    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.stale_worktree_entries == 1
    assert report.other_worktrees_examined == 0
    assert report.has_findings is False


def test_worktree_listing_failure_reports_no_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current"
    current.mkdir()
    fake = _make_fake_run_subprocess("", {}, listing_exit_code=1)
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.worktree_listing_failed is True
    assert report.has_findings is False


def test_one_unreadable_sibling_does_not_stop_the_rest_of_the_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-open per sibling: a broken git status on one worktree must not hide
    a real finding in another."""
    current = tmp_path / "current"
    current.mkdir()
    broken = tmp_path / "broken"
    broken.mkdir()
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    healthy_key = str(healthy.resolve())
    broken_key = str(broken.resolve())

    listing = (
        f"worktree {current.resolve()}\nworktree {broken.resolve()}\nworktree {healthy.resolve()}\n"
    )
    fake = _make_fake_run_subprocess(
        listing,
        {healthy_key: "?? .serena/memories/git/stray.md\n", broken_key: ""},
        status_exit_codes={broken_key: 128},
    )
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    report = checker.build_scope_report(current)

    assert report.unreadable_worktrees == 1
    # The unreadable sibling is NOT counted as examined: a summary line saying
    # two worktrees were scanned clean, next to a line saying one could not be
    # read, contradicts itself and hides the failure.
    assert report.other_worktrees_examined == 1
    assert report.findings == [
        checker.StrayMemoryFinding(worktree=healthy_key, relpath=".serena/memories/git/stray.md")
    ]


# --- format_report -----------------------------------------------------------


def test_format_report_names_the_finding_and_the_issue() -> None:
    report = checker.ScopeReport(
        current_worktree="/repo/current",
        other_worktrees_examined=1,
        findings=[
            checker.StrayMemoryFinding(worktree="/repo/sibling", relpath=".serena/memories/x.md")
        ],
    )

    text = checker.format_report(report)

    assert "#5061" in text
    assert "/repo/sibling" in text
    assert ".serena/memories/x.md" in text


def test_format_report_on_a_clean_scan_names_the_examined_count() -> None:
    report = checker.ScopeReport(current_worktree="/repo/current", other_worktrees_examined=3)

    text = checker.format_report(report)

    assert "0 finding(s)" in text
    assert "3 sibling worktree(s) examined" in text


def test_format_report_on_a_listing_failure_is_a_short_distinct_message() -> None:
    report = checker.ScopeReport(current_worktree="/repo/current", worktree_listing_failed=True)

    text = checker.format_report(report)

    assert "git worktree list failed" in text


def test_format_report_names_unreadable_siblings() -> None:
    report = checker.ScopeReport(
        current_worktree="/repo/current", other_worktrees_examined=1, unreadable_worktrees=1
    )

    text = checker.format_report(report)

    assert "1 sibling" in text
    assert "could not be read" in text


# --- validate_serena_memory_worktree_scope (advisory gate) ------------------


def test_the_advisory_gate_always_returns_true_even_with_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = tmp_path / "current"
    current.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    listing = f"worktree {current.resolve()}\nworktree {sibling.resolve()}\n"
    fake = _make_fake_run_subprocess(
        listing, {str(sibling.resolve()): "?? .serena/memories/git/stray.md\n"}
    )
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    result = checker.validate_serena_memory_worktree_scope(current)

    assert result is True
    assert "stray.md" in capsys.readouterr().out


# --- main() / CLI ------------------------------------------------------------


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True, cwd=path)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, cwd=path)
    subprocess.run(["git", "config", "user.name", "Test"], check=True, cwd=path)


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
    listing = f"worktree {current.resolve()}\nworktree {sibling.resolve()}\n"
    fake = _make_fake_run_subprocess(
        listing, {str(sibling.resolve()): "?? .serena/memories/git/stray.md\n"}
    )
    monkeypatch.setattr(checker, "_run_subprocess", fake)

    exit_code = checker.main(["--repo-root", str(current), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["relpath"] == ".serena/memories/git/stray.md"


# --- pre_pr_sequence wiring (testing.md SHOULD 6) ---------------------------


class _State:
    """Minimal stand-in for pre_pr.ValidationState."""

    def __init__(self) -> None:
        self.total = 0
        self.skipped = 0


def _run_gate_alone(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    verdicts: dict[str, bool] = {}

    def record(
        name: str,
        state: _State,
        callback: Callable[[], bool],
        skip: bool = False,
    ) -> bool:
        state.total += 1
        if skip:
            state.skipped += 1
            return True
        result = bool(callback())
        verdicts[name] = result
        return result

    wanted = [gate for gate in pre_pr_sequence._SEQUENCE if gate.name == GATE_NAME]
    monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", tuple(wanted))
    args = argparse.Namespace(quick=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, _State(), record)
    return verdicts


def test_the_gate_is_registered_in_the_sequence() -> None:
    names = [gate.name for gate in pre_pr_sequence._SEQUENCE]

    assert GATE_NAME in names


def test_the_sequence_runs_the_gate_and_it_stays_advisory_on_the_real_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drives the real sequence (real git, this repository's own worktrees).

    Read-only (``git worktree list`` / ``git status``), and the assertion is
    on the always-True advisory contract, not on what it happens to find, so
    this cannot flake on another concurrent session's worktree state.
    """
    verdicts = _run_gate_alone(monkeypatch)

    assert verdicts == {GATE_NAME: True}


# --- argv contract, bare repos, and fail-open (review findings) --------------


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
    fake = _make_fake_run_subprocess(listing, {}, record=calls)
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
    fake = _make_fake_run_subprocess(listing, {}, status_exit_codes={str(bare.resolve()): 128})
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
    fake = _make_fake_run_subprocess("", {}, listing_exit_code=128)
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
