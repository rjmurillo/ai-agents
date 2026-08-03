"""The unreachable-endingCommit error must not assert a cause it never checked.

Issue #4347, instance 2. ``commit_reachability_problem`` learns one thing: the
SHA is not an ancestor of HEAD. The diagnostic then told the reader the SHA was
"most likely orphaned by amending or rebasing" and to stop amending. This
repository merges by squash (ruleset 11104075 allows only the squash method),
so a squash merge orphans every branch SHA a session log records, and the
remedy named does not apply to the reader who hit it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import scripts.validate_session_json as vsj
from scripts.validation.models import ValidationResult


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repo_with_squash_merged_branch(tmp_path: Path) -> tuple[Path, str]:
    """Return a repo and a branch SHA orphaned by a squash merge.

    The branch commit still exists as an object and is still named by
    ``refs/heads/feature``. What it is not is an ancestor of HEAD, which is the
    only thing the reachability check measures.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    _git(repo, "config", "commit.gpgsign", "false")

    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "chore: base")

    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "b.txt").write_text("work\n", encoding="utf-8")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "feat: work")
    branch_sha = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "--squash", "feature")
    _git(repo, "commit", "-q", "-m", "feat: work (#1)")

    return repo, branch_sha


def _errors_for_ending_commit(repo: Path, sha: str, monkeypatch: Any) -> list[str]:  # noqa: ANN401
    monkeypatch.setattr(vsj, "_PROJECT_ROOT", repo)
    data = {
        "session": {"branch": "feature"},
        "protocolCompliance": {
            "sessionEnd": {"changesCommitted": {"complete": True, "evidence": "pushed"}}
        },
        "endingCommit": sha,
    }
    result = ValidationResult()
    vsj.validate_evidence_agrees_with_session(data, result)
    return result.errors


def test_squash_merged_sha_is_reported_without_blaming_an_amend(
    tmp_path: Path,
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo, branch_sha = _repo_with_squash_merged_branch(tmp_path)

    errors = _errors_for_ending_commit(repo, branch_sha, monkeypatch)

    assert len(errors) == 1
    message = errors[0]
    assert "not an ancestor of HEAD" in message
    assert "squash merged" in message
    assert "most likely orphaned by amending" not in message
    assert "instead of amending" not in message
    # `git cat-file -e` found the object before the ancestor test ran, so the
    # object is present here and "never pushed" is a cause the check ruled out.
    assert "never pushed" not in message


def test_reachable_sha_produces_no_error(
    tmp_path: Path,
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo, _ = _repo_with_squash_merged_branch(tmp_path)
    head = _git(repo, "rev-parse", "HEAD~1")

    assert _errors_for_ending_commit(repo, head, monkeypatch) == []


def test_unknown_sha_still_names_every_candidate_cause(
    tmp_path: Path,
    monkeypatch: Any,  # noqa: ANN401
) -> None:
    repo, _ = _repo_with_squash_merged_branch(tmp_path)
    absent = "0" * 40

    errors = _errors_for_ending_commit(repo, absent, monkeypatch)

    assert len(errors) == 1
    message = errors[0]
    assert "names no commit in this repository" in message
    assert "squash merged" in message
    assert "amended or rebased" in message
    assert "never pushed" in message
