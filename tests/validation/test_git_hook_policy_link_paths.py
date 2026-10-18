"""Tests for git_hook_policy._commit_link_paths (ADR-119 decision 14).

The pre-push security scan materializes pushed blobs. A tracked file link
(mode 120000) such as .claude/lib/paths.py holds a target path, not source, so
the scan leaves it out and scans the target under its own path.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

import git_hook_policy as policy
import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "linked.py").symlink_to("real.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_only_the_link_entry_is_reported(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert policy._commit_link_paths("HEAD", ["real.py", "linked.py"], repo) == {
        "linked.py": "real.py"
    }


def test_no_paths_means_no_git_call(tmp_path: Path) -> None:
    assert policy._commit_link_paths("not-a-ref", [], tmp_path) == {}


def test_an_unknown_head_returns_none(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert policy._commit_link_paths("no-such-ref", ["real.py"], repo) is None


def test_a_link_in_a_subdirectory_resolves_against_its_own_directory(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "lib").mkdir()
    (repo / "lib" / "mod.py").symlink_to("../real.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "sub")

    assert policy._commit_link_paths("HEAD", ["lib/mod.py"], repo) == {"lib/mod.py": "real.py"}


def test_a_link_that_leaves_the_repository_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "escape.py").symlink_to("../outside.py")
    (repo / "abs.py").symlink_to("/etc/passwd")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "escape")

    assert policy._commit_link_paths("HEAD", ["escape.py"], repo) is None
    assert policy._commit_link_paths("HEAD", ["abs.py"], repo) is None


def _arrange_scan(
    monkeypatch: pytest.MonkeyPatch, links: dict[str, str], tree: list[str]
) -> list[list[str]]:
    source = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", "2" * 40)
    update = policy.PushUpdate(source, "base", "head", "base..head", "a")
    monkeypatch.setattr(policy, "_push_updates", lambda *_a: [update])
    monkeypatch.setattr(policy, "_changed_commit_paths", lambda *_a: ["lib/paths.py", "other.py"])
    monkeypatch.setattr(policy, "_commit_paths", lambda *_a: tree)
    monkeypatch.setattr(policy, "_commit_link_paths", lambda *_a: links)
    monkeypatch.setattr(policy, "_pushed_root_moves", lambda *_a: set())
    monkeypatch.setattr(policy, "_container_clamped", lambda seconds: seconds)
    scanned: list[list[str]] = []

    def record(_head: str, paths: list[str], *_a: object, **_k: object) -> int:
        scanned.append(paths)
        return 0

    monkeypatch.setattr(policy, "_scan_pushed_head", record)
    return scanned


def test_the_scan_replaces_a_changed_link_with_its_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scanned = _arrange_scan(
        monkeypatch,
        {"lib/paths.py": "src/lib/paths.py"},
        ["lib/paths.py", "other.py", "src/lib/paths.py"],
    )

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0
    assert scanned == [["other.py", "src/lib/paths.py"]]


def test_the_scan_fails_closed_on_a_link_whose_target_is_not_in_the_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scanned = _arrange_scan(
        monkeypatch, {"lib/paths.py": "src/lib/gone.py"}, ["lib/paths.py", "other.py"]
    )

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 2
    assert scanned == []
