"""Chunked generated-file staging (issue #5437).

Windows rejects one ``git add`` whose command line passes 32767 characters
(``WinError 206``). ``stage_generated`` batches paths so no call grows with the
corpus, stages the same path set, and keeps its unsafe-path checks.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

WINDOWS_COMMAND_LIMIT = 32767
MEMORY_DIR = ".serena/memories"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "feature/test")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "user@example.com")
    _git(repo, "config", "core.quotepath", "off")
    return repo


def _write(repo: Path, relative_path: str, content: str = "x\n") -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))


def _long_name(index: int) -> str:
    return f"{MEMORY_DIR}/topic-{index:05d}-{'a' * 60}.md"


def _staged(repo: Path, *flags: str) -> list[str]:
    out = _git(repo, "diff", "--cached", "--name-only", "-z", *flags)
    return sorted(part for part in out.split("\0") if part)


def _record_add_calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    original = policy._run_git

    def spy(repo_root: Path, args: Sequence[str], **kwargs: float) -> object:
        if args and args[0] == "add":
            calls.append(list(args))
        return original(repo_root, args, **kwargs)

    monkeypatch.setattr(policy, "_run_git", spy)
    return calls


def test_chunk_paths_empty_yields_nothing() -> None:
    assert list(policy._chunk_paths([])) == []


def test_chunk_paths_single_chunk_when_under_budget() -> None:
    assert list(policy._chunk_paths(["a", "b", "c"], max_chars=100)) == [["a", "b", "c"]]


def test_chunk_paths_splits_without_losing_or_reordering_paths() -> None:
    paths = [f"p{n:03d}" for n in range(50)]

    chunks = list(policy._chunk_paths(paths, max_chars=40))

    assert len(chunks) > 1
    assert [path for chunk in chunks for path in chunk] == paths
    assert all(sum(len(p) + 1 for p in chunk) <= 40 for chunk in chunks)


def test_chunk_paths_oversize_path_gets_its_own_chunk() -> None:
    chunks = list(policy._chunk_paths(["a", "b" * 50, "c"], max_chars=10))

    assert chunks == [["a"], ["b" * 50], ["c"]]


def test_chunk_paths_budget_exactly_filled_does_not_split() -> None:
    assert list(policy._chunk_paths(["ab", "cd"], max_chars=6)) == [["ab", "cd"]]


def test_stage_generated_stages_corpus_past_windows_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    names = [_long_name(n) for n in range(2000)]
    for name in names:
        _write(repo, name)
    assert sum(len(name) + 1 for name in names) > WINDOWS_COMMAND_LIMIT
    calls = _record_add_calls(monkeypatch)

    assert policy.stage_generated("memory", repo) == 0

    assert _staged(repo) == sorted(names)
    assert len(calls) > 1
    assert all(sum(len(arg) + 1 for arg in call) < WINDOWS_COMMAND_LIMIT for call in calls)


def test_stage_generated_stages_names_with_spaces_and_newlines(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    names = [f"{MEMORY_DIR}/with space.md", f"{MEMORY_DIR}/line\nbreak.md"]
    for name in names:
        _write(repo, name)

    assert policy.stage_generated("memory", repo) == 0

    assert _staged(repo) == sorted(names)


def test_stage_generated_stages_tracked_deletions_across_chunks(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    names = [_long_name(n) for n in range(600)]
    for name in names:
        _write(repo, name)
    _git(repo, "add", "--", MEMORY_DIR)
    _git(repo, "commit", "-qm", "seed")
    deleted = names[:300]
    for name in deleted:
        (repo / name).unlink()
    for name in names[300:]:
        _write(repo, name, "changed\n")

    assert policy.stage_generated("memory", repo) == 0

    assert _staged(repo, "--diff-filter=D") == sorted(deleted)
    assert _staged(repo, "--diff-filter=M") == sorted(names[300:])


def test_stage_generated_stops_at_first_failing_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _init_repo(tmp_path)
    for n in range(400):
        _write(repo, _long_name(n))
    attempts: list[list[str]] = []

    def failing(repo_root: Path, args: Sequence[str], **kwargs: float) -> object:
        attempts.append(list(args))
        return subprocess.CompletedProcess(list(args), 7, "", "boom\n")

    monkeypatch.setattr(policy, "_run_git", failing)

    assert policy.stage_generated("memory", repo) == 7
    assert len([a for a in attempts if a[0] == "add"]) == 1
    captured = capsys.readouterr()
    assert "boom" in captured.err + captured.out


def test_stage_generated_unsafe_path_fails_closed_before_any_add(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _init_repo(tmp_path)
    _write(repo, f"{MEMORY_DIR}/ok.md")
    outside = tmp_path / "outside.md"
    outside.write_text("secret\n", encoding="utf-8")
    (repo / MEMORY_DIR / "link.md").symlink_to(outside)
    calls = _record_add_calls(monkeypatch)

    assert policy.stage_generated("memory", repo) == 2

    assert "unsafe path" in capsys.readouterr().err
    assert calls == []
    assert _staged(repo) == []


def test_stage_generated_nothing_to_stage_runs_no_add(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    calls = _record_add_calls(monkeypatch)

    assert policy.stage_generated("memory", repo) == 0
    assert calls == []
