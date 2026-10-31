"""Fail-closed anchors in the resume checker: worktree path and remote identity (issue #6506).

A relative Worktree, a non-URL Remote (including the no-origin sentinel), and a
Remote on a different host must hold instead of matching the live repository.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_handoff_resume as checker

REMOTE_URL = "https://github.com/rjmurillo/ai-agents.git"
BRANCH = "feat/anchors"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    root.mkdir()
    _git(root, "init", "-q", "-b", BRANCH)
    _git(root, "remote", "add", "origin", REMOTE_URL)
    (root / "f.txt").write_text("f", encoding="utf-8")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-qm", "first")
    return root.resolve()


def _write(path: Path, repo: Path, **overrides: str) -> Path:
    values = {
        "Remote": "rjmurillo/ai-agents",
        "Branch": BRANCH,
        "Worktree": str(repo),
        "Head SHA": _git(repo, "rev-parse", "HEAD"),
        "Timestamp": "2026-09-30T14:02Z",
        "Objective": "anchor checks",
        "Risk tier": "shared-repository",
        "Acceptance": "holds on bad anchors",
        "Phase": "implementing",
        "Next action": "run the checker",
        "Validation run": "unit tests pass",
        **overrides,
    }
    lines = ["# Handoff", "", "## State Record", ""]
    lines += [f"- **{key}**: {value}" for key, value in values.items()]
    lines += ["", "## Decisions Made", "", "- None", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _run(handoff: Path, repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = checker.main([str(handoff), "--repo", str(repo)])
    return code, capsys.readouterr().out


def test_relative_worktree_holds_even_when_it_resolves_to_live_tree(
    repo: Path, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo.parent)
    handoff = _write(tmp_path / "h.md", repo, Worktree=repo.name)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "worktree is not an absolute path" in out


def test_tilde_worktree_expands_to_an_absolute_path(
    repo: Path, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(repo.parent))
    handoff = _write(tmp_path / "h.md", repo, Worktree=f"~/{repo.name}")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK
    assert "[RESUME]" in out


@pytest.mark.parametrize(
    "recorded",
    ["(no origin remote)", "not a url", "justoneword", "a/b/c/d e"],
)
def test_non_url_remote_holds(repo: Path, tmp_path: Path, capsys, recorded: str) -> None:
    handoff = _write(tmp_path / "h.md", repo, Remote=recorded)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "remote is not a repository URL or owner/name" in out


def test_no_origin_sentinel_in_record_does_not_match_missing_origin(
    repo: Path, tmp_path: Path, capsys
) -> None:
    _git(repo, "remote", "remove", "origin")
    handoff = _write(tmp_path / "h.md", repo, Remote="(no origin remote)")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "remote is not a repository URL or owner/name" in out


def test_recorded_host_that_differs_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", repo, Remote="evil.example/rjmurillo/ai-agents")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "remote mismatch" in out


def test_live_host_that_differs_holds(repo: Path, tmp_path: Path, capsys) -> None:
    _git(repo, "remote", "set-url", "origin", "https://evil.example/rjmurillo/ai-agents.git")
    handoff = _write(tmp_path / "h.md", repo, Remote="github.com/rjmurillo/ai-agents")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "remote mismatch" in out


@pytest.mark.parametrize(
    "recorded",
    [
        "github.com/rjmurillo/ai-agents",
        "GitHub.com/RJMurillo/AI-Agents",
        "https://github.com/rjmurillo/ai-agents.git",
        "git@github.com:rjmurillo/ai-agents.git",
        "ssh://git@github.com/rjmurillo/ai-agents",
    ],
)
def test_matching_host_forms_resume(repo: Path, tmp_path: Path, capsys, recorded: str) -> None:
    handoff = _write(tmp_path / "h.md", repo, Remote=recorded)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK
    assert "[RESUME]" in out


def test_missing_origin_reports_no_origin(repo: Path, tmp_path: Path, capsys) -> None:
    _git(repo, "remote", "remove", "origin")
    handoff = _write(tmp_path / "h.md", repo)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "live (no origin remote)" in out


@pytest.mark.parametrize("origin", ["/home/x/repos/foo", "file:///srv/repos/foo"])
def test_non_url_live_origin_reports_the_url_not_missing_origin(
    repo: Path, tmp_path: Path, capsys, origin: str
) -> None:
    _git(repo, "remote", "set-url", "origin", origin)
    handoff = _write(tmp_path / "h.md", repo)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert f"live origin is not a repository URL: {origin}" in out
    assert "no origin remote" not in out
