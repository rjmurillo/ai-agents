"""Real git regression tests for worktree garbage collection."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.maintenance import gc_worktrees


@dataclass(frozen=True, slots=True)
class GitSandbox:
    """A disposable repository with an origin remote and linked worktrees."""

    root: Path
    main: Path
    remote: Path


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write_and_commit(cwd: Path, relative_path: str, content: str, message: str) -> None:
    path = cwd / relative_path
    path.write_text(content, encoding="utf-8")
    _git(cwd, "add", relative_path)
    _git(cwd, "commit", "-m", message)


@pytest.fixture
def git_sandbox() -> Iterator[GitSandbox]:
    temp_parent = Path(__file__).resolve().parents[1] / ".pytest_tmp" / "gc_worktrees"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gc-worktrees-", dir=temp_parent) as temp_dir:
        root = Path(temp_dir)
        remote = root / "origin.git"
        main = root / "repo"
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(remote)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "clone", str(remote), str(main)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        _git(main, "config", "user.email", "test@example.com")
        _git(main, "config", "user.name", "Test User")
        _git(main, "config", "commit.gpgsign", "false")
        _write_and_commit(main, "base.txt", "base\n", "base")
        _git(main, "push", "-u", "origin", "main")
        yield GitSandbox(root=root, main=main, remote=remote)


def _run_gc_json(
    sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    monkeypatch.chdir(sandbox.main)
    code = gc_worktrees.main(["--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    return json.loads(captured.out)


def _decision_for(report: dict[str, object], path: Path) -> dict[str, object]:
    decisions = report["decisions"]
    assert isinstance(decisions, list)
    matches = [d for d in decisions if isinstance(d, dict) and d["path"] == str(path)]
    assert len(matches) == 1
    return matches[0]


def _add_worktree_branch(sandbox: GitSandbox, branch: str) -> Path:
    worktree = sandbox.root / branch.replace("/", "-")
    _git(sandbox.main, "worktree", "add", "-b", branch, str(worktree))
    return worktree


def _create_squash_merged_branch(sandbox: GitSandbox, branch: str = "feat/squash") -> Path:
    worktree = _add_worktree_branch(sandbox, branch)
    _write_and_commit(worktree, "feature.txt", f"{branch}\n", "feature")
    _git(worktree, "push", "-u", "origin", branch)
    _git(sandbox.main, "merge", "--squash", branch)
    _git(sandbox.main, "commit", "-m", "squash feature")
    _git(sandbox.main, "push", "origin", "main")
    _git(sandbox.main, "push", "origin", f":{branch}")
    _git(sandbox.main, "fetch", "--prune", "origin")
    return worktree


def test_squash_merged_branch_with_deleted_origin_head_is_removable(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox)

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is True
    assert decision["reason"] == "merged by deleted upstream"


def test_unmerged_unpushed_branch_with_existing_origin_head_is_kept(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _add_worktree_branch(git_sandbox, "feat/unmerged")
    _write_and_commit(worktree, "published.txt", "published\n", "published")
    _git(worktree, "push", "-u", "origin", "feat/unmerged")
    _write_and_commit(worktree, "local.txt", "local\n", "local")

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_UNPUSHED


def test_clean_detached_ancestor_worktree_is_removable(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = git_sandbox.root / "detached-main"
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "origin/main")

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["branch"] is None
    assert decision["remove"] is True
    assert decision["reason"] == "merged to base"


def test_dirty_squash_merged_branch_is_kept(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox, "feat/dirty")
    (worktree / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_DIRTY


def test_remote_head_failure_uses_ancestry_only_behavior(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox, "feat/offline")
    _git(git_sandbox.main, "remote", "set-url", "origin", str(git_sandbox.root / "missing"))

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert report["remote_head_lookup_failed"] is True
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_UNPUSHED

    code = gc_worktrees.main([])
    captured = capsys.readouterr()
    assert code == 0
    assert "remote head lookup failed, using ancestry-only merge checks" in captured.out


def test_squash_detection_is_load_bearing_negative_control(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox, "feat/control")

    with patch(
        "scripts.maintenance.gc_worktrees._gc_remote.is_merged_by_deleted_upstream",
        return_value=False,
    ):
        report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_UNPUSHED


def _make_stale_worktree(sandbox: GitSandbox, branch: str) -> tuple[Path, str]:
    """Register a worktree, commit in it, then delete the directory."""
    worktree = _add_worktree_branch(sandbox, branch)
    _write_and_commit(worktree, "work.txt", f"{branch}\n", "work")
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    shutil.rmtree(worktree)
    return worktree, head


def test_a_stale_entry_is_a_prune_candidate_not_an_inspection_failure(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The plan must name a stale entry, not report that git could not read it."""
    worktree, _ = _make_stale_worktree(git_sandbox, "feat/stale")

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is True
    assert decision["reason"] == gc_worktrees.PRUNE_STALE


def test_git_worktree_remove_really_works_on_a_stale_entry(
    git_sandbox: GitSandbox,
) -> None:
    """The load-bearing assumption behind per-path removal.

    Dropping the blanket ``git worktree prune`` is only safe because
    ``git worktree remove`` accepts an entry whose directory is already gone.
    That is a claim about git itself, so it is pinned against real git rather
    than a mock.
    """
    worktree, head = _make_stale_worktree(git_sandbox, "feat/stale-remove")
    listing = _git(git_sandbox.main, "worktree", "list", "--porcelain").stdout
    assert "prunable" in listing

    subprocess.run(
        ["git", "worktree", "remove", str(worktree)],
        cwd=git_sandbox.main,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    remaining = _git(git_sandbox.main, "worktree", "list", "--porcelain").stdout
    assert str(worktree) not in remaining
    assert _git(git_sandbox.main, "cat-file", "-t", head).stdout.strip() == "commit"
