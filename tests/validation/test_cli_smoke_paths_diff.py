"""Diff and match-report tests for the CLI smoke path filter (REQ-047 AC10).

The three-dot diff takes full SHAs only, fails closed on a git error, and the
match report lists matches in diff order up to a cap.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import cli_smoke_paths as paths

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA_A = "a" * 40
_SHA_B = "b" * 40


def _stub_git(
    monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str] | Exception
) -> list[list[str]]:
    """Replace ``subprocess.run`` in the module; return the argv lists it saw."""
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(paths.subprocess, "run", fake_run)
    return seen


def _completed(code: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], code, stdout=stdout, stderr=stderr)


def test_changed_files_lists_the_three_dot_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_git(monkeypatch, _completed(0, stdout="a.md\n\nsrc/claude/x.md\n"))

    assert paths.changed_files(_SHA_A, _SHA_B, _REPO_ROOT) == ["a.md", "src/claude/x.md"]
    assert f"{_SHA_A}...{_SHA_B}" in seen[0]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (_completed(128, stderr="bad object"), "bad object"),
        (OSError("git missing"), "git diff did not run: OSError"),
        (subprocess.TimeoutExpired(cmd="git", timeout=1), "git diff did not run: TimeoutExpired"),
    ],
    ids=["nonzero-exit", "oserror", "timeout"],
)
def test_changed_files_raises_when_git_fails(
    result: subprocess.CompletedProcess[str] | Exception,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_git(monkeypatch, result)

    with pytest.raises(paths.DiffError, match=message):
        paths.changed_files(_SHA_A, _SHA_B, _REPO_ROOT)


@pytest.mark.parametrize("bad", ["", "main", "--output=x", "abc", "g" * 40, "A" * 40, "a" * 39])
def test_changed_files_rejects_a_non_sha_revision(bad: str) -> None:
    with pytest.raises(paths.DiffError, match="40-character"):
        paths.changed_files(bad, _SHA_B, _REPO_ROOT)
    with pytest.raises(paths.DiffError, match="40-character"):
        paths.changed_files(_SHA_A, bad, _REPO_ROOT)


def test_matched_paths_keeps_only_matches_in_order() -> None:
    changed = ["README.md", "src/claude/b.md", "docs/x.md", "src/claude/a.md"]
    assert paths.matched_paths(changed) == ["src/claude/b.md", "src/claude/a.md"]
    assert paths.matched_paths(["README.md"]) == []


@pytest.mark.parametrize("extra", [0, 5])
def test_describe_matches_caps_and_counts_the_rest(extra: int) -> None:
    matched = [f"src/claude/{i}.md" for i in range(paths.MAX_LISTED_PATHS + extra)]
    lines = paths.describe_matches(matched).splitlines()

    assert len(lines) == paths.MAX_LISTED_PATHS + (1 if extra else 0)
    assert (lines[-1] == f"  and {extra} more") if extra else all("more" not in x for x in lines)
