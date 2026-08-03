"""Non-fast-forward push detection in ``git_hook_policy`` (issue #4293).

The pre-push hook receives ``local_ref local_sha remote_ref remote_sha`` on
stdin and never sees argv, so a force push is only visible as an ancestry
relation: the remote tip is not reachable from the local tip.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from scripts.validation import git_hook_policy as policy

ZERO_SHA = "0" * 40
ABSENT_SHA = "1" * 40


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _git(repo, "add", "--", name)
    _git(repo, "commit", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


def _push_ref(
    local_sha: str,
    remote_sha: str,
    remote_ref: str = "refs/heads/feature",
) -> policy.PushRef:
    return policy.PushRef(
        local_ref="refs/heads/feature",
        local_sha=local_sha,
        remote_ref=remote_ref,
        remote_sha=remote_sha,
    )


def _rewritten_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Return (repo, published_sha, rewritten_sha) where neither reaches the other."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit(repo, "base.txt")
    published = _commit(repo, "published.txt")
    _git(repo, "reset", "--hard", base)
    rewritten = _commit(repo, "rewritten.txt")
    return repo, published, rewritten


def test_fast_forward_update_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    first = _commit(repo, "first.txt")
    second = _commit(repo, "second.txt")

    assert policy._check_non_fast_forward(_push_ref(second, first), repo) == 0


def test_new_branch_with_zero_remote_sha_passes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit(repo, "first.txt")

    assert policy._check_non_fast_forward(_push_ref(head, ZERO_SHA), repo) == 0


def test_deletion_passes_through_to_the_protected_destination_check(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit(repo, "first.txt")

    assert policy._check_non_fast_forward(_push_ref(ZERO_SHA, head), repo) == 0


def test_non_branch_destination_is_not_checked(tmp_path: Path) -> None:
    repo, published, rewritten = _rewritten_repo(tmp_path)

    push_ref = _push_ref(rewritten, published, remote_ref="refs/tags/v1")

    assert policy._check_non_fast_forward(push_ref, repo) == 0


def test_history_rewrite_is_rejected(tmp_path: Path) -> None:
    repo, published, rewritten = _rewritten_repo(tmp_path)

    assert policy._check_non_fast_forward(_push_ref(rewritten, published), repo) == 1


def test_history_rewrite_message_names_both_shas(tmp_path: Path, capsys) -> None:
    repo, published, rewritten = _rewritten_repo(tmp_path)

    policy._check_non_fast_forward(_push_ref(rewritten, published), repo)

    stderr = capsys.readouterr().err
    assert "non-fast-forward" in stderr
    assert published in stderr
    assert rewritten in stderr


def test_absent_remote_object_blocks_and_says_to_fetch(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit(repo, "first.txt")

    result = policy._check_non_fast_forward(_push_ref(head, ABSENT_SHA), repo)

    assert result == 1
    assert "Fetch the remote and retry" in capsys.readouterr().err


def test_escape_hatch_allows_the_rewrite_and_warns(tmp_path: Path, capsys, monkeypatch) -> None:
    repo, published, rewritten = _rewritten_repo(tmp_path)
    monkeypatch.setenv(policy.FORCE_PUSH_ESCAPE_ENV, "1")

    result = policy._check_non_fast_forward(_push_ref(rewritten, published), repo)

    assert result == 0
    assert "unrecoverable" in capsys.readouterr().err


def test_escape_hatch_only_fires_for_the_exact_value(tmp_path: Path, monkeypatch) -> None:
    repo, published, rewritten = _rewritten_repo(tmp_path)
    monkeypatch.setenv(policy.FORCE_PUSH_ESCAPE_ENV, "true")

    assert policy._check_non_fast_forward(_push_ref(rewritten, published), repo) == 1


def test_check_push_refs_rejects_a_rewrite_on_the_second_ref(
    tmp_path: Path, monkeypatch
) -> None:
    """Wiring test: the guard must run inside the only branch-protection funnel."""
    repo, published, rewritten = _rewritten_repo(tmp_path)
    monkeypatch.setattr(policy, "check_active_git_operation", lambda _root: 0)
    monkeypatch.setattr(policy, "check_branch", lambda _root: 0)
    monkeypatch.setattr(policy, "_check_history_integrity", lambda _root: 0)
    monkeypatch.setattr(policy, "_fetch_origin_main", lambda _root: None)
    monkeypatch.setattr(policy, "_check_push_updates", lambda _updates, _root: 0)

    stream = io.StringIO(
        f"refs/heads/clean {published} refs/heads/clean {ZERO_SHA}\n"
        f"refs/heads/feature {rewritten} refs/heads/feature {published}\n"
    )

    assert policy.check_push_refs(stream, repo) == 1


def test_check_push_refs_allows_a_clean_multi_ref_push(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    first = _commit(repo, "first.txt")
    second = _commit(repo, "second.txt")
    monkeypatch.setattr(policy, "check_active_git_operation", lambda _root: 0)
    monkeypatch.setattr(policy, "check_branch", lambda _root: 0)
    monkeypatch.setattr(policy, "_check_history_integrity", lambda _root: 0)
    monkeypatch.setattr(policy, "_fetch_origin_main", lambda _root: None)
    monkeypatch.setattr(policy, "_check_push_updates", lambda _updates, _root: 0)

    stream = io.StringIO(
        f"refs/heads/clean {first} refs/heads/clean {ZERO_SHA}\n"
        f"refs/heads/feature {second} refs/heads/feature {first}\n"
    )

    assert policy.check_push_refs(stream, repo) == 0
