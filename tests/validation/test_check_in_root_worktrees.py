"""Worktrees living inside a checkout of the same repository (issue #4702).

Agent worktrees under `.claude/worktrees/` made every recursive scan multiply
its count by the number of live worktrees. These tests drive a real git
repository for the acceptance pair (in-root fails, sibling passes) and use
fixture directories for the edge cases.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_in_root_worktrees as checker

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real repository with one commit, so `git worktree add` works."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "i",
    )
    return root


def make_worktree_dir(parent: Path, name: str) -> Path:
    """Create a directory carrying the `.git` file `git worktree add` writes."""
    path = parent / name
    path.mkdir(parents=True)
    (path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
    return path


# --- acceptance: real git ---------------------------------------------------


def test_a_worktree_inside_the_repo_root_fails(repo: Path) -> None:
    _git(repo, "worktree", "add", "-q", "-b", "a", str(repo / ".claude" / "worktrees" / "agent-a"))

    report = checker.build_report(repo)

    assert report.has_findings
    assert [w.registered for w in report.worktrees] == [True]
    assert report.worktrees[0].parent == str(repo.resolve())
    assert checker.main(["--repo-root", str(repo)]) == 1


def test_a_sibling_worktree_passes(repo: Path) -> None:
    _git(repo, "worktree", "add", "-q", "-b", "b", str(repo.parent / "repo-worktrees" / "b"))

    report = checker.build_report(repo)

    assert not report.has_findings
    assert report.registered_count == 2
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_a_nested_worktree_is_reported_against_its_innermost_parent(repo: Path) -> None:
    outer = repo.parent / "outer"
    inner = outer / ".claude" / "worktrees" / "inner"
    _git(repo, "worktree", "add", "-q", "-b", "outer", str(outer))
    _git(repo, "worktree", "add", "-q", "-b", "inner", str(inner))

    report = checker.build_report(repo)

    assert [(w.path, w.parent) for w in report.worktrees] == [
        (str(inner.resolve()), str(outer.resolve()))
    ]


# --- find_nested_registered -------------------------------------------------


def test_the_innermost_parent_wins_at_three_levels(tmp_path: Path) -> None:
    a = tmp_path / "r"
    b = a / ".claude/worktrees/b"
    c = b / ".claude/worktrees/c"

    found = checker.find_nested_registered([str(a), str(b), str(c)])

    assert [(Path(w.path).name, Path(w.parent).name) for w in found] == [("b", "r"), ("c", "b")]


def test_a_prefix_sharing_sibling_is_not_nested(tmp_path: Path) -> None:
    """`repo-worktrees` shares a string prefix with `repo` but is not inside it."""
    found = checker.find_nested_registered(
        [str(tmp_path / "repo"), str(tmp_path / "repo-worktrees")]
    )

    assert found == []


def test_an_empty_registered_list_finds_nothing() -> None:
    assert checker.find_nested_registered([]) == []


def test_an_unresolvable_registered_path_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "_resolve", lambda raw: None if raw == "bad" else Path(raw))

    assert checker.find_nested_registered(["bad", str(tmp_path)]) == []


@pytest.mark.parametrize("error", [OSError("gone"), RuntimeError("symlink loop")])
def test_resolve_returns_none_when_the_filesystem_cannot_answer(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(self: Path, strict: bool = False) -> Path:
        raise error

    monkeypatch.setattr(Path, "resolve", boom)

    assert checker._resolve("/anything") is None


# --- orphan half --------------------------------------------------------------


@pytest.mark.parametrize("container", checker.CONTAINER_DIRS)
def test_an_orphan_in_each_container_is_reported(tmp_path: Path, container: str) -> None:
    orphan = make_worktree_dir(tmp_path / container, "wt_orphan")

    report = checker.scan_repo_root(tmp_path, [str(tmp_path)], git_listing_failed=False)

    assert [(w.path, w.registered) for w in report.worktrees] == [(str(orphan), False)]


def test_a_registered_worktree_is_not_double_counted_as_an_orphan(tmp_path: Path) -> None:
    wt = make_worktree_dir(tmp_path / ".claude/worktrees", "agent-x")

    report = checker.scan_repo_root(tmp_path, [str(tmp_path), str(wt)], git_listing_failed=False)

    assert [w.registered for w in report.worktrees] == [True]


def test_a_plain_clone_inside_the_root_is_not_a_worktree(tmp_path: Path) -> None:
    (tmp_path / ".worktrees" / "clone" / ".git").mkdir(parents=True)

    report = checker.scan_repo_root(tmp_path, [], git_listing_failed=False)

    assert report.worktrees == []
    assert report.examined >= 1


def test_a_deep_orphan_outside_the_scan_scope_is_not_walked(tmp_path: Path) -> None:
    """Scope is one level under each container, which keeps the scan cheap."""
    make_worktree_dir(tmp_path / "src" / "deep", "wt")

    assert checker.scan_repo_root(tmp_path, [], git_listing_failed=False).worktrees == []


def test_an_unlistable_container_is_counted_and_disclosed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".wt").mkdir()
    real_iterdir = Path.iterdir

    def iterdir(self: Path):
        if self.name == ".wt":
            raise PermissionError("denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    report = checker.scan_repo_root(tmp_path, [], git_listing_failed=False)

    assert report.unreadable_entries == 1
    assert "unreadable" in checker.format_report(report)


def test_an_unstattable_entry_is_counted_not_examined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "bad").mkdir()
    real_is_dir = Path.is_dir

    def is_dir(self: Path) -> bool:
        if self.name == "bad":
            raise PermissionError("denied")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", is_dir)
    report = checker.scan_repo_root(tmp_path, [], git_listing_failed=False)

    assert report.unreadable_entries == 1
    assert report.examined == 0


# --- git failures -------------------------------------------------------------


def test_a_nonzero_git_exit_is_a_listing_failure(tmp_path: Path) -> None:
    """tmp_path is not a repository, so git exits non-zero."""
    report = checker.build_report(tmp_path)

    assert report.git_listing_failed
    assert "incomplete" in checker.format_report(report)


def test_a_git_failure_does_not_suppress_the_orphan_half(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path / ".claude/worktrees", "agent-y")

    report = checker.build_report(tmp_path)

    assert report.git_listing_failed
    assert [w.registered for w in report.worktrees] == [False]


@pytest.mark.parametrize("error", [OSError("no git"), subprocess.TimeoutExpired("git", 10)])
def test_a_git_launch_failure_is_a_listing_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(checker.subprocess, "run", boom)

    assert checker._list_registered(tmp_path) == ([], True)


# --- report, gate, CLI ----------------------------------------------------------


def test_the_report_names_the_rule_the_parent_and_the_repair(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path / ".claude/worktrees", "agent-z")

    text = checker.format_report(checker.scan_repo_root(tmp_path, [], git_listing_failed=False))

    assert "MUST NOT 6" in text
    assert "git worktree move" in text
    assert f"inside {tmp_path}" in text
    assert "orphaned" in text


def test_a_clean_report_still_names_the_examined_count(tmp_path: Path) -> None:
    text = checker.format_report(checker.scan_repo_root(tmp_path, [], git_listing_failed=False))

    assert "0 in-root worktree(s)" in text
    assert "examined entries" in text


def test_the_advisory_gate_never_fails_even_with_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    make_worktree_dir(tmp_path / ".claude/worktrees", "agent-q")

    assert checker.validate_in_root_worktrees(tmp_path) is True
    assert "agent-q" in capsys.readouterr().out


def test_build_report_runs_against_the_real_repository() -> None:
    report = checker.build_report(REPO_ROOT)

    assert not report.git_listing_failed
    assert report.registered_count >= 1


def test_main_exits_two_on_a_missing_repo_root(tmp_path: Path) -> None:
    assert checker.main(["--repo-root", str(tmp_path / "missing")]) == 2


def test_main_defaults_to_this_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []

    def fake(root: Path) -> checker.InRootReport:
        seen.append(root)
        return checker.InRootReport(repo_root=str(root), examined=0, registered_count=1)

    monkeypatch.setattr(checker, "build_report", fake)

    assert checker.main([]) == 0
    assert seen == [REPO_ROOT]


def test_main_emits_json_when_asked(repo: Path, capsys: pytest.CaptureFixture) -> None:
    checker.main(["--repo-root", str(repo), "--json"])

    assert '"registered_count": 1' in capsys.readouterr().out


def test_module_runs_as_a_script(repo: Path) -> None:
    script = REPO_ROOT / "scripts" / "validation" / "check_in_root_worktrees.py"
    result = subprocess.run(
        ["python3", str(script), "--repo-root", str(repo)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "0 in-root worktree(s)" in result.stdout


# --- review round 1: submodules, missing directories, git failure exit ---------


def test_a_submodule_is_not_reported_as_an_orphaned_worktree(tmp_path: Path) -> None:
    """A submodule's `.git` file points under `.git/modules/`, not `worktrees/`."""
    sub = tmp_path / "libfoo"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../.git/modules/libfoo\n", encoding="utf-8")

    report = checker.scan_repo_root(tmp_path, [str(tmp_path)], git_listing_failed=False)

    assert report.worktrees == []
    assert checker.is_linked_worktree_dir(sub) is False


def test_a_windows_style_worktree_pointer_is_recognised(tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: C:\\repo\\.git\\worktrees\\wt\n", encoding="utf-8")

    assert checker.is_linked_worktree_dir(wt) is True


def test_an_unreadable_pointer_is_not_a_linked_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt = make_worktree_dir(tmp_path, "wt")
    monkeypatch.setattr(checker, "is_worktree_dir", lambda _p: True)
    real_open = Path.open

    def deny(self: Path, *args, **kwargs):
        if self.name == ".git":
            raise PermissionError("denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)

    assert checker.is_linked_worktree_dir(wt) is False


def test_a_registered_worktree_with_a_missing_directory_gets_prune_advice(
    repo: Path, tmp_path: Path
) -> None:
    gone = repo / ".claude" / "worktrees" / "gone"
    _git(repo, "worktree", "add", "-q", "-b", "gone", str(gone))
    gone.rename(tmp_path / "moved-away")

    report = checker.build_report(repo)
    text = checker.format_report(report)

    assert [w.missing for w in report.worktrees] == [True]
    assert "git worktree prune" in text


def test_exists_counts_an_unanswerable_stat_as_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: Path) -> bool:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "exists", boom)

    assert checker._exists(Path("/anything")) is True


def test_main_exits_three_when_git_fails_and_nothing_is_found(tmp_path: Path) -> None:
    """A failed listing is unproved, not clean (tmp_path is not a repository)."""
    assert checker.main(["--repo-root", str(tmp_path)]) == 3


def test_main_exits_one_when_git_fails_but_an_orphan_is_found(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path / ".claude/worktrees", "agent-f")

    assert checker.main(["--repo-root", str(tmp_path)]) == 1


def test_findings_are_labelled_unverified_when_git_failed(tmp_path: Path) -> None:
    make_worktree_dir(tmp_path / ".claude/worktrees", "agent-u")

    text = checker.format_report(checker.build_report(tmp_path))

    assert "unverified (git listing failed)" in text
    assert "orphaned" not in text
