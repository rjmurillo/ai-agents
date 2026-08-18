"""Worktrees living under the temp root, and a low temp free-space floor (issue #5111).

Six orphaned worktrees plus pytest scratch filled a 16G tmpfs to 4.0K free.
Transcript writes then failed with ENOSPC and a backgrounded `git push` failed
while its wrapper reported exit 0. The issue records that `git worktree list`
showed zero entries under `/tmp` at the time, so the filesystem half of this
scan is the half that would have caught it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_tmp_worktrees as checker

REPO_ROOT = Path(__file__).resolve().parents[2]
_GIB = 1024**3


def make_worktree_dir(parent: Path, name: str) -> Path:
    """Create a directory carrying the `.git` file `git worktree add` writes."""
    path = parent / name
    path.mkdir()
    (path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
    return path


# --- parse_worktree_list --------------------------------------------------


def test_parse_worktree_list_reads_every_worktree_line() -> None:
    porcelain = (
        "worktree /home/u/repo\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree /tmp/pr5010-work\nHEAD def\ndetached\n"
    )

    assert checker.parse_worktree_list(porcelain) == ["/home/u/repo", "/tmp/pr5010-work"]


@pytest.mark.parametrize("porcelain", ["", "   ", "\n\n"])
def test_parse_worktree_list_handles_empty_input(porcelain: str) -> None:
    assert checker.parse_worktree_list(porcelain) == []


def test_parse_worktree_list_ignores_non_worktree_lines() -> None:
    assert checker.parse_worktree_list("HEAD abc\nbare\ndetached\n") == []


# --- is_worktree_dir ------------------------------------------------------


def test_a_gitdir_file_marks_a_worktree(tmp_path: Path) -> None:
    assert checker.is_worktree_dir(make_worktree_dir(tmp_path, "wt")) is True


def test_a_git_directory_is_a_clone_not_a_worktree(tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)

    assert checker.is_worktree_dir(clone) is False


def test_a_directory_without_git_is_not_a_worktree(tmp_path: Path) -> None:
    plain = tmp_path / "baseline_check"
    plain.mkdir()

    assert checker.is_worktree_dir(plain) is False


def test_a_git_file_with_other_content_is_not_a_worktree(tmp_path: Path) -> None:
    odd = tmp_path / "odd"
    odd.mkdir()
    (odd / ".git").write_text("not a gitdir pointer\n", encoding="utf-8")

    assert checker.is_worktree_dir(odd) is False


def test_a_missing_directory_is_not_a_worktree(tmp_path: Path) -> None:
    assert checker.is_worktree_dir(tmp_path / "gone") is False


# --- find_registered_temp_worktrees ---------------------------------------


def test_registered_paths_under_the_temp_root_are_selected(tmp_path: Path) -> None:
    inside = tmp_path / "wt"
    inside.mkdir()

    found = checker.find_registered_temp_worktrees([str(inside), "/home/u/repo"], tmp_path)

    assert found == [str(inside)]


def test_registered_paths_outside_the_temp_root_are_ignored(tmp_path: Path) -> None:
    assert checker.find_registered_temp_worktrees(["/home/u/repo"], tmp_path) == []


def test_an_empty_registered_list_selects_nothing(tmp_path: Path) -> None:
    assert checker.find_registered_temp_worktrees([], tmp_path) == []


# --- scan_temp_root: positive ---------------------------------------------


def test_an_orphaned_worktree_is_reported_without_git_knowing_it(tmp_path: Path) -> None:
    # The issue #5111 shape: on disk, absent from `git worktree list`.
    make_worktree_dir(tmp_path, "pr5010-work")

    report = checker.scan_temp_root(tmp_path, 0, registered=[], git_listing_failed=False)

    assert [w.path for w in report.worktrees] == [str(tmp_path / "pr5010-work")]
    assert report.worktrees[0].registered is False
    assert report.has_findings is True


def test_a_registered_worktree_is_labelled_registered(tmp_path: Path) -> None:
    path = make_worktree_dir(tmp_path, "wt")

    report = checker.scan_temp_root(tmp_path, 0, [str(path)], git_listing_failed=False)

    assert report.worktrees[0].registered is True


def test_a_registered_worktree_whose_directory_is_gone_is_still_reported(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "vanished"

    report = checker.scan_temp_root(tmp_path, 0, [str(missing)], git_listing_failed=False)

    assert [w.path for w in report.worktrees] == [str(missing)]


def test_free_space_below_the_floor_is_a_finding(tmp_path: Path) -> None:
    # A floor larger than any real disk forces the low-space branch.
    report = checker.scan_temp_root(tmp_path, 10**18, [], git_listing_failed=False)

    assert report.free_space_low is True
    assert report.has_findings is True
    assert "below the" in checker.format_report(report)


# --- scan_temp_root: negative ---------------------------------------------


def test_a_clean_temp_root_has_no_findings(tmp_path: Path) -> None:
    (tmp_path / "ordinary-scratch").mkdir()
    (tmp_path / "a-file.log").write_text("x", encoding="utf-8")

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert report.worktrees == []
    assert report.free_space_low is False
    assert report.has_findings is False
    assert report.examined == 1, "files must not count as examined directories"


def test_an_empty_temp_root_reports_zero_examined(tmp_path: Path) -> None:
    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert report.examined == 0
    assert report.has_findings is False


# --- scan_temp_root: edge cases -------------------------------------------


def test_a_missing_temp_root_is_reported_as_absent_not_as_clean(tmp_path: Path) -> None:
    report = checker.scan_temp_root(tmp_path / "gone", 0, [], git_listing_failed=False)

    assert report.temp_root_present is False
    assert report.examined == 0
    assert report.has_findings is False
    assert "nothing examined" in checker.format_report(report)


def test_a_git_failure_is_disclosed_and_does_not_suppress_the_filesystem_half(
    tmp_path: Path,
) -> None:
    make_worktree_dir(tmp_path, "orphan")

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=True)

    assert len(report.worktrees) == 1
    assert "git worktree list failed" in checker.format_report(report)


def test_the_free_space_floor_boundary_is_exclusive(tmp_path: Path) -> None:
    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)
    assert report.free_bytes is not None

    at_floor = checker.scan_temp_root(tmp_path, report.free_bytes, [], git_listing_failed=False)
    below_floor = checker.scan_temp_root(
        tmp_path, report.free_bytes + 1, [], git_listing_failed=False
    )

    assert at_floor.free_space_low is False, "free == floor is not below the floor"
    assert below_floor.free_space_low is True


# --- error branches -------------------------------------------------------


def test_an_unreadable_git_marker_is_not_a_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = make_worktree_dir(tmp_path, "wt")

    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "open", explode)

    assert checker.is_worktree_dir(worktree) is False


def test_an_unresolvable_registered_path_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("too many levels of symbolic links")

    monkeypatch.setattr(Path, "resolve", explode)

    assert checker.find_registered_temp_worktrees(["/tmp/wt"], tmp_path) == []


def test_a_nonzero_git_exit_is_reported_as_a_listing_failure(tmp_path: Path) -> None:
    # tmp_path is not a git repository, so `git worktree list` exits non-zero.
    paths, failed = checker._list_registered(tmp_path)

    assert (paths, failed) == ([], True)


def test_a_git_launch_failure_is_reported_as_a_listing_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", explode)

    assert checker._list_registered(tmp_path) == ([], True)


def test_an_unlistable_temp_root_is_counted_and_disclosed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "iterdir", explode)

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert report.unreadable_entries == 1
    assert report.examined == 0
    assert "were unreadable" in checker.format_report(report)


def test_an_unstattable_entry_is_counted_not_examined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "entry"
    entry.mkdir()
    real_is_dir = Path.is_dir

    def explode_for_the_entry(self: Path, *args: object, **kwargs: object) -> bool:
        if self == entry:
            raise OSError("stale file handle")
        return bool(real_is_dir(self, *args, **kwargs))

    monkeypatch.setattr(Path, "is_dir", explode_for_the_entry)

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert report.unreadable_entries == 1
    assert report.examined == 0


def test_an_unreadable_temp_root_is_not_reported_as_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> bool:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "is_dir", explode)

    report = checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False)

    assert report.temp_root_present is False
    assert report.unreadable_entries == 1, "an unreadable root must not read as absent"


def test_unreadable_free_space_is_reported_as_unknown_not_as_low(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("no such device")

    monkeypatch.setattr(checker.shutil, "disk_usage", explode)

    report = checker.scan_temp_root(tmp_path, 10**18, [], git_listing_failed=False)

    assert report.free_bytes is None
    assert report.free_space_low is False, "unknown free space must not read as low"
    assert "free space unreadable" in checker.format_report(report)


# --- format_report --------------------------------------------------------


def test_the_report_always_names_the_examined_count(tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()

    text = checker.format_report(checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False))

    assert "1 examined entries" in text


def test_the_report_cites_the_rule_and_the_repair_command(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path, "wt")

    text = checker.format_report(checker.scan_temp_root(tmp_path, 0, [], git_listing_failed=False))

    assert "MUST NOT 7" in text
    assert "git worktree move" in text


# --- build_report and the advisory gate -----------------------------------


def test_build_report_runs_against_the_real_repository(tmp_path: Path) -> None:
    report = checker.build_report(REPO_ROOT, temp_root=tmp_path, min_free_gib=0)

    assert report.temp_root == str(tmp_path)
    assert report.git_listing_failed is False


def test_the_advisory_gate_never_fails_even_with_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    make_worktree_dir(tmp_path, "wt")
    monkeypatch.setattr(checker, "DEFAULT_TEMP_ROOT", tmp_path)

    verdict = checker.validate_tmp_worktrees(REPO_ROOT)

    # The negative control: the gate must have SEEN the planted worktree and
    # still returned True. Without this assertion the test passes even when
    # the monkeypatch does not reach the scan, which is the vacuous shape.
    assert "wt" in capsys.readouterr().out
    assert verdict is True


# --- CLI exit codes -------------------------------------------------------


def test_main_exits_zero_on_a_clean_temp_root(tmp_path: Path) -> None:
    assert checker.main(["--temp-root", str(tmp_path), "--min-free-gib", "0"]) == 0


def test_main_exits_one_when_a_worktree_sits_under_the_temp_root(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path, "pr5025-worktree")

    assert checker.main(["--temp-root", str(tmp_path), "--min-free-gib", "0"]) == 1


def test_main_exits_one_when_free_space_is_below_the_floor(tmp_path: Path) -> None:
    assert checker.main(["--temp-root", str(tmp_path), "--min-free-gib", "1e9"]) == 1


def test_main_exits_two_on_a_missing_explicit_temp_root(tmp_path: Path) -> None:
    assert checker.main(["--temp-root", str(tmp_path / "gone")]) == 2


def test_main_exits_two_on_a_negative_floor(tmp_path: Path) -> None:
    assert checker.main(["--temp-root", str(tmp_path), "--min-free-gib", "-1"]) == 2


def test_main_emits_json_when_asked(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    checker.main(["--temp-root", str(tmp_path), "--min-free-gib", "0", "--json"])

    assert '"examined"' in capsys.readouterr().out


def test_module_runs_as_a_script(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path, "wt")
    script = REPO_ROOT / "scripts" / "validation" / "check_tmp_worktrees.py"

    result = subprocess.run(
        ["python3", str(script), "--temp-root", str(tmp_path), "--min-free-gib", "0"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "examined entries" in result.stdout
