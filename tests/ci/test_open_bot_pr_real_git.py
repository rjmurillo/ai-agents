"""Run scripts/ci/open_bot_pr.py against real git and a bare remote.

The other test files fake git, so they prove the argv shape and not that git
accepts the sequence. Here only `gh` is faked. Each test builds a bare origin
and a clone in a temp directory, so nothing touches the real repository.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from open_bot_pr import main
finally:
    sys.path[:] = _original_path

_REAL_RUN = subprocess.run
_BRANCH = "automation/stats"
_STATS = ".serena/stats.md"
_REPORT = ".metrics/report.md"


def _git(cwd: Path, *args: str) -> str:
    result = _REAL_RUN(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


class _FakeGh:
    """Real git passes through. gh pr list and gh pr create are faked."""

    def __init__(self, open_prs: str = "[]") -> None:
        self.open_prs = open_prs
        self.created: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] != "gh":
            passthrough = {k: v for k, v in kwargs.items() if k != "errors"}
            return _REAL_RUN(argv, errors="replace", **passthrough)
        if argv[1:3] == ["pr", "list"]:
            return subprocess.CompletedProcess(argv, 0, self.open_prs, "")
        if argv[1:3] == ["pr", "create"]:
            self.created.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "https://github.com/o/r/pull/1\n", "")
        raise AssertionError(f"unexpected gh command: {argv}")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.name", "seed")
    _git(work, "config", "user.email", "seed@example.com")
    _git(work, "checkout", "-b", "main")
    for path in (_STATS, _REPORT):
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text("v1\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "-u", "origin", "main")
    monkeypatch.chdir(work)
    return origin, work


def _argv(artifact: Path) -> list[str]:
    return [
        "--path",
        _STATS,
        "--path",
        _REPORT,
        "--user-name",
        "bot",
        "--user-email",
        "bot@example.com",
        "--message",
        "chore(stats): update",
        "--message",
        "body",
        "--branch",
        _BRANCH,
        "--issue",
        "234",
        "--artifact-dir",
        str(artifact),
    ]


def _artifact(tmp_path: Path, version: str, files: tuple[str, ...] = (_STATS, _REPORT)) -> Path:
    root = tmp_path / f"artifact-{version}"
    for path in files:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(f"{version}\n", encoding="utf-8")
    return root


def _remote_file(origin: Path, ref: str, path: str) -> str:
    return _git(origin, "show", f"{ref}:{path}")


def test_publish_pushes_the_bot_branch_and_leaves_main_alone(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, _ = repo
    gh = _FakeGh()
    monkeypatch.setattr(subprocess, "run", gh)
    main_before = _git(origin, "rev-parse", "refs/heads/main")
    assert main(_argv(_artifact(tmp_path, "v2"))) == 0
    assert _git(origin, "rev-parse", "refs/heads/main") == main_before
    assert _remote_file(origin, f"refs/heads/{_BRANCH}", _STATS) == "v2"
    assert _remote_file(origin, f"refs/heads/{_BRANCH}", _REPORT) == "v2"
    assert _git(origin, "log", "-1", "--format=%an", f"refs/heads/{_BRANCH}") == "bot"
    assert len(gh.created) == 1


def test_only_the_changed_file_lands_when_the_artifact_holds_one(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, _ = repo
    monkeypatch.setattr(subprocess, "run", _FakeGh())
    artifact = _artifact(tmp_path, "v2")
    (artifact / _REPORT).write_text("v1\n", encoding="utf-8")  # unchanged from the seed
    assert main(_argv(artifact)) == 0
    changed = _git(origin, "diff", "--name-only", "main", f"refs/heads/{_BRANCH}")
    assert changed == _STATS


def test_a_stale_remote_branch_with_no_open_pr_is_replaced_without_force(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, work = repo
    gh = _FakeGh()
    monkeypatch.setattr(subprocess, "run", gh)
    assert main(_argv(_artifact(tmp_path, "v2"))) == 0
    first_tip = _git(origin, "rev-parse", f"refs/heads/{_BRANCH}")
    _git(work, "checkout", "main")
    assert main(_argv(_artifact(tmp_path, "v3"))) == 0
    second_tip = _git(origin, "rev-parse", f"refs/heads/{_BRANCH}")
    assert second_tip != first_tip
    assert _remote_file(origin, f"refs/heads/{_BRANCH}", _STATS) == "v3"
    assert len(gh.created) == 2


def test_an_open_pr_leaves_the_remote_branch_untouched(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, work = repo
    monkeypatch.setattr(subprocess, "run", _FakeGh())
    assert main(_argv(_artifact(tmp_path, "v2"))) == 0
    tip = _git(origin, "rev-parse", f"refs/heads/{_BRANCH}")
    _git(work, "checkout", "main")
    open_pr = '[{"url": "https://github.com/o/r/pull/1", "isCrossRepository": false}]'
    gh = _FakeGh(open_prs=open_pr)
    monkeypatch.setattr(subprocess, "run", gh)
    assert main(_argv(_artifact(tmp_path, "v3"))) == 0
    assert _git(origin, "rev-parse", f"refs/heads/{_BRANCH}") == tip
    assert gh.created == []


def test_a_forged_extra_file_in_the_artifact_never_reaches_the_commit(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, work = repo
    monkeypatch.setattr(subprocess, "run", _FakeGh())
    artifact = _artifact(tmp_path, "v2")
    (artifact / "scripts/ci").mkdir(parents=True)
    (artifact / "scripts/ci/open_bot_pr.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    assert main(_argv(artifact)) == 0
    files = _git(origin, "ls-tree", "-r", "--name-only", f"refs/heads/{_BRANCH}").splitlines()
    assert "scripts/ci/open_bot_pr.py" not in files
    assert not (work / "scripts").exists()


def test_head_ahead_of_origin_main_refuses_to_publish(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin, work = repo
    (work / "extra.txt").write_text("local only\n", encoding="utf-8")
    _git(work, "add", "extra.txt")
    _git(work, "commit", "-m", "unpublished local commit")
    monkeypatch.setattr(subprocess, "run", _FakeGh())
    assert main(_argv(_artifact(tmp_path, "v2"))) == 2
    assert _git(origin, "branch", "--list", _BRANCH) == ""
