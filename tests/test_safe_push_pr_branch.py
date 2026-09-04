#!/usr/bin/env python3
# taste-lint: ignore file-size, this suite exercises one CLI contract end to end.
"""Tests for ``.github/scripts/safe_push_pr_branch.py`` (issue #3412)."""

from __future__ import annotations

import builtins
import importlib.util
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from scripts.test_selection.select_tests import Selection
from scripts.validation import git_hook_policy

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / ".github" / "scripts" / "safe_push_pr_branch.py"
)
_spec = importlib.util.spec_from_file_location("safe_push_pr_branch", _MODULE_PATH)
assert _spec and _spec.loader
safe_push_pr_branch = importlib.util.module_from_spec(_spec)
sys.modules["safe_push_pr_branch"] = safe_push_pr_branch
_spec.loader.exec_module(safe_push_pr_branch)

SafePushError = safe_push_pr_branch.SafePushError
safe_push = safe_push_pr_branch.safe_push
main = safe_push_pr_branch.main
EXIT_OK = safe_push_pr_branch.EXIT_OK
EXIT_VERIFICATION = safe_push_pr_branch.EXIT_VERIFICATION
EXIT_TRANSPORT = safe_push_pr_branch.EXIT_TRANSPORT
EXIT_USAGE = safe_push_pr_branch.EXIT_USAGE
FULL_SHA1 = "a" * 40
FULL_SHA256 = "b" * 64


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )
    return result.stdout.strip()


def _bare_git(bare: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "--git-dir", str(bare), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _init_worktree(repo: Path, branch: str) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", branch)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")


def _bare_remote(tmp_path: Path, name: str = "remote.git") -> Path:
    bare = tmp_path / name
    subprocess.run(
        ["git", "init", "-q", "--bare", str(bare)],
        check=True,
        capture_output=True,
    )
    return bare


def _commit_file(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# Unit: porcelain parsing and sha extraction
# ---------------------------------------------------------------------------


def test_parse_porcelain_keeps_source_destination_and_summary() -> None:
    stdout = "To https://example/repo.git\n \tHEAD:refs/heads/foo\t1111111..2222222\nDone\n"

    refs = safe_push_pr_branch._parse_porcelain(stdout)

    assert len(refs) == 1
    assert refs[0].source == "HEAD"
    assert refs[0].destination == "refs/heads/foo"
    assert refs[0].summary == "1111111..2222222"


def test_parse_porcelain_ignores_headers_and_blank_lines() -> None:
    refs = safe_push_pr_branch._parse_porcelain("To url\n\nDone\n")

    assert refs == []


def test_extract_new_sha_parses_fast_forward_update_range() -> None:
    assert safe_push_pr_branch._extract_new_sha("1111111..2222222") == (
        "1111111",
        "2222222",
    )


def test_extract_new_sha_parses_force_update_range() -> None:
    assert safe_push_pr_branch._extract_new_sha("1111111...2222222") == (
        "1111111",
        "2222222",
    )


def test_extract_new_sha_returns_none_for_new_branch() -> None:
    assert safe_push_pr_branch._extract_new_sha("[new branch]") == (None, None)


def test_single_porcelain_ref_rejects_unexpected_source() -> None:
    audit = safe_push_pr_branch.PushAudit(
        branch="feature-x",
        remote="origin",
        requested_refspec="HEAD:refs/heads/feature-x",
        local_sha="a" * 40,
        process_id=1,
    )
    refs = [
        safe_push_pr_branch.PorcelainRef(
            flag=" ",
            source="refs/heads/main",
            destination="refs/heads/feature-x",
            summary="1111111..2222222",
            old_sha="1111111",
            new_sha="2222222",
        )
    ]

    with pytest.raises(SafePushError) as excinfo:
        safe_push_pr_branch._require_single_porcelain_ref(
            refs, "a" * 40, "refs/heads/feature-x", audit
        )

    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert "exactly one porcelain ref" in str(excinfo.value)


def test_single_porcelain_ref_rejects_duplicate_refs() -> None:
    audit = safe_push_pr_branch.PushAudit(
        branch="feature-x",
        remote="origin",
        requested_refspec="HEAD:refs/heads/feature-x",
        local_sha="a" * 40,
        process_id=1,
    )
    refs = [
        safe_push_pr_branch.PorcelainRef(" ", "a" * 40, "refs/heads/feature-x", "", None, None),
        safe_push_pr_branch.PorcelainRef("=", "a" * 40, "refs/heads/feature-x", "", None, None),
    ]

    with pytest.raises(SafePushError) as excinfo:
        safe_push_pr_branch._require_single_porcelain_ref(
            refs, "a" * 40, "refs/heads/feature-x", audit
        )

    assert excinfo.value.exit_code == EXIT_VERIFICATION


def test_module_imports_without_fcntl(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "fcntl":
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    module_name = "safe_push_pr_branch_no_fcntl"
    spec = importlib.util.spec_from_file_location(module_name, _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    assert hasattr(module, "safe_push")


# ---------------------------------------------------------------------------
# Positive: real push to a bare remote verifies and audits
# ---------------------------------------------------------------------------


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_push_updates_requested_ref_and_reports_verified(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    local_sha = _git(repo, "rev-parse", "HEAD")

    audit = safe_push("feature-x", "origin", str(repo))

    assert audit.verified is True
    assert audit.branch == "feature-x"
    assert audit.requested_refspec == f"{local_sha}:refs/heads/feature-x"
    assert audit.local_sha == local_sha
    assert audit.observed_remote_sha == local_sha
    assert audit.process_id > 0
    assert audit.transport_text
    assert _bare_git(bare, "rev-parse", "refs/heads/feature-x") == local_sha


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_push_uses_resolved_sha_when_head_moves_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    original_sha = _git(repo, "rev-parse", "HEAD")
    interloper_sha: str | None = None
    push_args: list[str] = []
    mutated = False
    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(
        args: list[str], repo_root: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        nonlocal interloper_sha, mutated, push_args
        if args == ["rev-parse", "--verify", "HEAD"] and not mutated:
            interloper_sha = _commit_file(Path(repo_root), "interloper.txt", "interloper\n")
            mutated = True
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=f"{original_sha}\n",
                stderr="",
            )
        if args and args[0] == "push":
            push_args = args
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    audit = safe_push("feature-x", "origin", str(repo))

    assert interloper_sha is not None
    assert audit.requested_refspec == f"{original_sha}:refs/heads/feature-x"
    assert push_args[-1] == f"{original_sha}:refs/heads/feature-x"
    assert _git(repo, "rev-parse", "HEAD") == interloper_sha
    assert _bare_git(bare, "rev-parse", "refs/heads/feature-x") == original_sha
    assert _bare_git(bare, "rev-parse", "refs/heads/feature-x") != interloper_sha


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_audit_records_full_remote_sha_on_update(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(repo))
    local_sha = _commit_file(repo, "next.txt", "next\n")

    audit = safe_push("feature-x", "origin", str(repo))

    assert audit.verified is True
    assert audit.remote_new_sha == local_sha
    assert audit.observed_remote_sha == local_sha


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_force_with_lease_pushes_only_expected_remote_sha(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(repo))
    expected_sha = _bare_git(bare, "rev-parse", "refs/heads/feature-x")
    local_sha = _commit_file(repo, "next.txt", "next\n")

    _git(repo, "reset", "--hard", "HEAD~1")
    _commit_file(repo, "rewrite.txt", "rewrite\n")
    rewritten_sha = _git(repo, "rev-parse", "HEAD")
    assert rewritten_sha != local_sha

    audit = safe_push(
        "feature-x",
        "origin",
        str(repo),
        expected_remote_sha=expected_sha,
        force_with_lease=True,
    )

    assert audit.verified is True
    assert audit.remote_old_sha is not None
    assert audit.observed_remote_sha == rewritten_sha


# ---------------------------------------------------------------------------
# Negative controls
# ---------------------------------------------------------------------------


def test_push_fails_when_transport_names_a_different_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "fix-3377")
    _git(repo, "remote", "add", "origin", str(bare))

    local_sha = _git(repo, "rev-parse", "HEAD")
    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(
        args: list[str], repo_root: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=(
                    "To https://example/repo.git\n"
                    f" \t{local_sha}:refs/heads/fix-3383\taaaaaaa..bbbbbbb\n"
                    "Done\n"
                ),
                stderr="",
            )
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    with pytest.raises(SafePushError) as excinfo:
        safe_push("fix-3377", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert "exactly one porcelain ref" in str(excinfo.value)
    assert excinfo.value.audit.local_sha == _git(repo, "rev-parse", "HEAD")


def test_push_checks_git_returncode_before_porcelain_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))

    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(
        args: list[str], repo_root: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=128,
                stdout="hook stdout without porcelain\n",
                stderr="transport failed\n",
            )
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_TRANSPORT
    assert excinfo.value.audit.local_sha == _git(repo, "rev-parse", "HEAD")
    assert excinfo.value.audit.returncode == 128
    assert "transport failed" in excinfo.value.audit.stderr
    assert "hook stdout" in excinfo.value.audit.transport_text


def test_push_fails_when_ls_remote_mismatches_local_after_successful_porcelain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    local_sha = _git(repo, "rev-parse", "HEAD")
    other_sha = "b" * 40

    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(
        args: list[str], repo_root: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=(
                    "To https://example/repo.git\n"
                    f" \t{local_sha}:refs/heads/feature-x\t{local_sha[:7]}..{local_sha[:7]}\n"
                    "Done\n"
                ),
                stderr="",
            )
        if args[:2] == ["ls-remote", "--refs"]:
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=f"{other_sha}\trefs/heads/feature-x\n",
                stderr="",
            )
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert excinfo.value.audit.observed_remote_sha == other_sha
    assert "expected local sha" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Edge: wrong-branch and detached-HEAD guards refuse before pushing
# ---------------------------------------------------------------------------


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_push_refuses_when_head_on_other_branch(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))

    with pytest.raises(SafePushError) as excinfo:
        safe_push("some-other-branch", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert "HEAD is on" in str(excinfo.value)
    refs = _bare_git(bare, "for-each-ref", "--format=%(refname)")
    assert "some-other-branch" not in refs


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_push_refuses_on_detached_head_even_when_branch_is_head(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "HEAD")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "checkout", "-q", "--detach")

    with pytest.raises(SafePushError) as excinfo:
        safe_push("HEAD", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_USAGE
    refs = _bare_git(bare, "for-each-ref", "--format=%(refname)")
    assert "refs/heads/HEAD" not in refs


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_push_fails_on_non_fast_forward_rejection(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(repo))

    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(bare), str(other))
    _git(other, "config", "user.email", "t@example.com")
    _git(other, "config", "user.name", "T")
    _git(other, "checkout", "-q", "feature-x")
    _commit_file(other, "adv.txt", "adv\n")
    _git(other, "push", "-q", "origin", "feature-x")

    _commit_file(repo, "local.txt", "local\n")

    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_TRANSPORT


# ---------------------------------------------------------------------------
# Regression: same-destination race uses one PR branch
# ---------------------------------------------------------------------------


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_concurrent_worktrees_same_destination_detects_competing_update(
    tmp_path: Path,
) -> None:
    bare = _bare_remote(tmp_path)
    seed = tmp_path / "seed"
    _init_worktree(seed, "feature-x")
    _git(seed, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(seed))

    wt_a = tmp_path / "wt-a"
    wt_b = tmp_path / "wt-b"
    _git(tmp_path, "clone", "-q", str(bare), str(wt_a))
    _git(tmp_path, "clone", "-q", str(bare), str(wt_b))
    for wt, tag in ((wt_a, "a"), (wt_b, "b")):
        _git(wt, "config", "user.email", f"{tag}@example.com")
        _git(wt, "config", "user.name", f"Worker {tag}")
        _git(wt, "checkout", "-q", "feature-x")
        _commit_file(wt, f"{tag}.txt", f"{tag}\n")

    barrier = threading.Barrier(2)
    results: dict[str, Any] = {}
    errors: dict[str, Any] = {}

    def worker(wt: Path, name: str) -> None:
        barrier.wait(timeout=10)
        try:
            results[name] = safe_push("feature-x", "origin", str(wt))
        except SafePushError as exc:
            errors[name] = exc

    threads = [
        threading.Thread(target=worker, args=(wt_a, "a")),
        threading.Thread(target=worker, args=(wt_b, "b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert len(results) == 1
    assert len(errors) == 1
    assert next(iter(errors.values())).exit_code in {EXIT_TRANSPORT, EXIT_VERIFICATION}
    remote_sha = _bare_git(bare, "rev-parse", "refs/heads/feature-x")
    assert remote_sha == next(iter(results.values())).local_sha


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_argument_parser_docstring_matches_bad_argument_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    docstring = safe_push_pr_branch.SafePushArgumentParser.__doc__ or ""

    code = main(["--branch", "feature-x", "--unknown-option"])

    assert "raises SafePushError with EXIT_USAGE" in docstring
    assert code == EXIT_USAGE
    assert "unrecognized arguments" in capsys.readouterr().err


def test_main_rejects_flag_shaped_branch(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--branch=--force", "--repo-root", "."]) == EXIT_USAGE


def _successful_audit(branch: str, remote: str, repo_root: str, **kwargs: Any) -> Any:
    return safe_push_pr_branch.PushAudit(
        branch=branch,
        remote=remote,
        requested_refspec=f"{FULL_SHA1}:refs/heads/{branch}",
        local_sha=FULL_SHA1,
        process_id=1,
        verified=True,
        expected_remote_sha=kwargs.get("expected_remote_sha"),
    )


@pytest.mark.parametrize(
    ("sha", "expected_code"),
    [
        (FULL_SHA1, EXIT_OK),
        (FULL_SHA256, EXIT_OK),
        ("abcdef12", EXIT_USAGE),
        ("origin/main", EXIT_USAGE),
        ("HEAD", EXIT_USAGE),
        ("", EXIT_USAGE),
        ("g" * 40, EXIT_USAGE),
    ],
)
def test_main_validates_expected_remote_sha_at_parse_time(
    sha: str,
    expected_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_safe_push(
        branch: str,
        remote: str,
        repo_root: str,
        expected_remote_sha: str | None = None,
        force_with_lease: bool = False,
    ) -> Any:
        calls.append(
            {
                "branch": branch,
                "remote": remote,
                "repo_root": repo_root,
                "expected_remote_sha": expected_remote_sha,
                "force_with_lease": force_with_lease,
            }
        )
        return _successful_audit(
            branch,
            remote,
            repo_root,
            expected_remote_sha=expected_remote_sha,
        )

    monkeypatch.setattr(safe_push_pr_branch, "safe_push", fake_safe_push)

    code = main(
        [
            "--branch",
            "feature-x",
            "--repo-root",
            ".",
            "--force-with-lease",
            "--expected-remote-sha",
            sha,
        ]
    )

    assert code == expected_code
    if expected_code == EXIT_OK:
        assert calls == [
            {
                "branch": "feature-x",
                "remote": "origin",
                "repo_root": ".",
                "expected_remote_sha": sha,
                "force_with_lease": True,
            }
        ]
    else:
        assert calls == []
        assert "full 40 or 64 character hexadecimal object id" in capsys.readouterr().err


def test_safe_push_rejects_invalid_expected_remote_sha_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    calls: list[list[str]] = []
    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(
        args: list[str], repo_root: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    with pytest.raises(SafePushError) as excinfo:
        safe_push(
            "feature-x",
            "origin",
            str(repo),
            expected_remote_sha="origin/main",
            force_with_lease=True,
        )

    assert excinfo.value.exit_code == EXIT_USAGE
    assert [args for args in calls if args and args[0] == "push"] == []


@pytest.mark.safe_push_transport
@pytest.mark.integration
def test_main_success_emits_notice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))

    code = main(["--branch", "feature-x", "--remote", "origin", "--repo-root", str(repo)])

    assert code == EXIT_OK
    captured = capsys.readouterr()
    assert "pushed feature-x" in captured.out
    assert '"requested_refspec"' in captured.err
    assert '"process_id"' in captured.err
    assert '"local_sha"' in captured.err


def test_main_failure_emits_populated_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(
        args: list[str], repo_root: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=128,
                stdout="stdout payload\n",
                stderr="stderr payload\n",
            )
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    code = main(["--branch", "feature-x", "--remote", "origin", "--repo-root", str(repo)])

    assert code == EXIT_TRANSPORT
    captured = capsys.readouterr()
    assert '"local_sha": ""' not in captured.err
    assert '"returncode": 128' in captured.err
    assert '"stderr": "stderr payload\\n"' in captured.err
    assert "stdout payload" in captured.err


# ---------------------------------------------------------------------------
# Criterion 2: pre-push validation excludes real-transport integration tests
# ---------------------------------------------------------------------------


def _pytest_marker_and_paths(command: list[str]) -> tuple[str, list[str], list[str]]:
    """Split a pytest argv into its marker expression, targets, and ignores.

    Parsing the argv instead of comparing it verbatim keeps the guard on the
    two invariants that carry the safety (which marker deselects run, and which
    module is targeted versus ignored) while tolerating benign additions such
    as ``-q`` or ``--maxfail``.

    Flags whose value is a separate argv token are consumed as pairs. Without
    that, the ``auto`` in ``-n auto`` and the ``loadfile`` in ``--dist
    loadfile`` (issue #4823) parse as bare words and land in ``targets``, which
    would report the bulk command as targeting two paths that do not exist.
    """
    value_flags = frozenset({"-m", "--ignore", "-n", "--numprocesses", "--dist"})
    marker = ""
    targets: list[str] = []
    ignores: list[str] = []
    index = 0
    while index < len(command):
        token = command[index]
        if token in value_flags:
            if token == "-m":
                marker = command[index + 1]
            elif token == "--ignore":
                ignores.append(command[index + 1])
            index += 2
            continue
        if token.startswith("--ignore="):
            ignores.append(token.split("=", 1)[1])
            index += 1
            continue
        if not token.startswith("-") and index > 2:
            targets.append(token)
        index += 1
    return marker, targets, ignores


def test_pre_push_pytest_commands_include_safe_push_module() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    mutation_tests = str(repo_root / "tests" / "mutation")
    safe_push_tests = str(repo_root / "tests" / "test_safe_push_pr_branch.py")
    mutation_signal_tests = str(repo_root / "tests" / "test_mutation_workspace_signals.py")
    pr_autofix_tests = str(repo_root / "tests" / "test_pr_autofix_late_live_state_gate.py")

    commands = git_hook_policy._pytest_commands(repo_root)
    parsed = [_pytest_marker_and_paths(command) for command in commands]

    for command in commands:
        assert command[:3] == [sys.executable, "-m", "pytest"]

    bulk = [entry for entry in parsed if safe_push_tests in entry[2]]
    mutation_targeted = [entry for entry in parsed if mutation_tests in entry[1]]
    targeted = [entry for entry in parsed if safe_push_tests in entry[1]]
    pr_autofix_targeted = [entry for entry in parsed if pr_autofix_tests in entry[1]]

    assert len(bulk) == 1, parsed
    assert len(mutation_targeted) == 1, parsed
    assert len(targeted) == 1, parsed
    assert len(pr_autofix_targeted) == 1, parsed

    bulk_marker, bulk_targets, _ = bulk[0]
    assert bulk_marker == "not integration"
    assert str(repo_root / "tests") in bulk_targets
    assert mutation_tests in bulk[0][2]
    assert mutation_signal_tests in bulk[0][2]
    assert pr_autofix_tests in bulk[0][2]

    mutation_marker, mutation_targets, mutation_ignores = mutation_targeted[0]
    assert mutation_marker == "not integration"
    assert mutation_targets == [mutation_tests]
    assert mutation_tests not in mutation_ignores

    targeted_marker, targeted_targets, targeted_ignores = targeted[0]
    assert targeted_marker == "not integration and not safe_push_transport"
    assert safe_push_tests not in targeted_ignores
    assert mutation_signal_tests in targeted_targets
    assert mutation_signal_tests not in targeted_ignores
    assert pr_autofix_tests not in targeted_targets

    pr_autofix_marker, _, pr_autofix_ignores = pr_autofix_targeted[0]
    assert pr_autofix_marker == "not integration"
    assert pr_autofix_tests not in pr_autofix_ignores

    # The transport tests must never run under pre-push, so no command may
    # reach this module without deselecting the safe_push_transport marker.
    for marker, targets, ignores in parsed:
        if safe_push_tests in ignores:
            continue
        reaches_module = safe_push_tests in targets or str(repo_root / "tests") in targets
        if reaches_module:
            assert "not integration" in marker, (marker, targets)
            assert "not safe_push_transport" in marker, (marker, targets)


def test_safe_push_partition_is_the_serial_one(tmp_path: Path) -> None:
    """Parallelism (issue #4823) must not reach the safe-push partition.

    That partition targets the process-sensitive push and signal modules. Its
    narrower marker expression deselects the real-transport tests. The full policy, worker
    count, and the CI half live in
    ``tests/validation/test_pytest_parallelism_policy.py`` and
    ``tests/workflows/test_pytest_xdist_parallelism.py``; this assertion sits
    next to the transport-exclusion guard above because both protect the same
    command.
    """
    bulk, mutation, safe_push, pr_autofix = git_hook_policy._pytest_commands(tmp_path)

    assert "-n" in bulk and "--dist" in bulk
    assert "-n" in mutation and "--dist" in mutation
    assert str(tmp_path / "tests" / "mutation") in mutation
    assert "-n" not in safe_push
    assert "--numprocesses" not in safe_push
    assert "--dist" not in safe_push
    assert str(tmp_path / "tests" / "test_safe_push_pr_branch.py") in safe_push
    assert str(tmp_path / "tests" / "test_mutation_workspace_signals.py") in safe_push
    assert str(tmp_path / "tests" / "test_pr_autofix_late_live_state_gate.py") in pr_autofix
    assert "-n" not in pr_autofix
    assert "--numprocesses" not in pr_autofix
    assert "--dist" not in pr_autofix


def test_object_id_validator_loads_from_real_module() -> None:
    validator = safe_push_pr_branch._load_object_id_validator()

    assert validator(FULL_SHA1) is True
    assert validator("abcdef12") is False


def test_object_id_validator_missing_symbol_names_path(tmp_path: Path) -> None:
    module_path = tmp_path / "object_id.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        safe_push_pr_branch._load_object_id_validator(module_path)

    message = str(excinfo.value)
    assert "does not define is_full_object_id" in message
    assert str(module_path) in message
    assert excinfo.value.__cause__ is not None
    assert isinstance(excinfo.value.__cause__, KeyError)


def test_object_id_validator_non_callable_symbol_names_path(tmp_path: Path) -> None:
    module_path = tmp_path / "object_id.py"
    module_path.write_text("is_full_object_id = 3\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        safe_push_pr_branch._load_object_id_validator(module_path)

    message = str(excinfo.value)
    assert "non-callable" in message
    assert str(module_path) in message


def test_object_id_validator_absent_file_names_path(tmp_path: Path) -> None:
    module_path = tmp_path / "missing_object_id.py"

    with pytest.raises(RuntimeError) as excinfo:
        safe_push_pr_branch._load_object_id_validator(module_path)

    assert str(module_path) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_object_id_validator_unparsable_module_names_path(tmp_path: Path) -> None:
    module_path = tmp_path / "object_id.py"
    module_path.write_text("def is_full_object_id(:\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        safe_push_pr_branch._load_object_id_validator(module_path)

    assert str(module_path) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, SyntaxError)


# ---------------------------------------------------------------------------
# Pre-push suite timeout is a whole-suite budget, not a per-command timeout
# ---------------------------------------------------------------------------


def _record_pytest_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    *,
    elapsed_per_command: float,
    returncode: int = 0,
) -> list[float]:
    seen: list[float] = []
    clock = {"now": 1_000.0}

    # The budget-sharing contract these tests pin only exists when `run_pytest`
    # builds more than one command, which is the executing partition set. The
    # default pre-push path builds a single collection command instead
    # (ADR-104), so opt into local execution to keep the multi-command
    # behaviour under test rather than asserting it against one command.
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")

    # Pin the workstation contract. `run_pytest` now clamps the aggregate
    # budget, not just each child, so inside a container these numbers would be
    # the 150s ceiling rather than the budget under test. This suite also runs
    # inside dev containers, so without this the assertions would read the
    # clamp and quietly stop testing what they name. The clamped case has its
    # own test below.
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)

    def fake_monotonic() -> float:
        return clock["now"]

    def fake_run_command(
        args: Any,
        repo_root: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        seen.append(kwargs["timeout_seconds"])
        clock["now"] += elapsed_per_command
        return subprocess.CompletedProcess(list(args), returncode, "", "")

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda result: None)
    return seen


def test_run_pytest_shares_one_timeout_budget_across_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    budget = git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    spent = 30.0
    seen = _record_pytest_timeouts(monkeypatch, elapsed_per_command=spent)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert len(seen) == len(git_hook_policy._pytest_commands(tmp_path))
    assert seen[0] == pytest.approx(budget)
    for index, timeout in enumerate(seen):
        assert timeout == pytest.approx(budget - spent * index)
    assert sum(seen) <= budget * len(seen)
    assert seen[-1] < budget


def test_run_pytest_gives_the_collection_stand_in_the_smaller_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The default pre-push path is bounded by collection, not by the suite.

    `_pytest_budget_seconds` is unit-tested next to the selector; this is the
    end-to-end pin that `run_pytest` actually hands that budget to the child,
    because the deadline arithmetic sits between the two and a regression
    there would restore a 29-minute ceiling on a push that never runs a test.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    # Workstation contract: the aggregate is now clamped in a container, and
    # this suite also runs inside dev containers, so the assertion would read
    # the 150s ceiling instead of the collection budget it names.
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    seen: list[float] = []

    def fake_run_command(args: Any, repo_root: Any, **kwargs: Any):
        seen.append(kwargs["timeout_seconds"])
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda result: None)

    assert git_hook_policy.run_pytest(tmp_path) == 0

    assert len(seen) == 1
    assert seen[0] <= git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
    assert seen[0] > git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS - 5


def test_run_pytest_refuses_to_start_a_command_past_the_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    budget = git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    seen = _record_pytest_timeouts(monkeypatch, elapsed_per_command=budget + 1)

    assert git_hook_policy.run_pytest(tmp_path) == 1

    assert len(seen) == 1
    assert "exceeded" in capsys.readouterr().err


def test_run_pytest_stops_on_the_first_failing_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen = _record_pytest_timeouts(
        monkeypatch,
        elapsed_per_command=1.0,
        returncode=3,
    )

    assert git_hook_policy.run_pytest(tmp_path) == 3
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# Budget exhaustion message (#4472)
# ---------------------------------------------------------------------------


def test_a_container_bounds_the_whole_pytest_step_not_just_each_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The failure the per-child clamp did not cover.

    `_run_command` bounds one subprocess. An import-graph subset emits up to
    four partition commands and takes the execution budget, so before this the
    step could spend 4 * 150s = 600s inside a container against the ~679s at
    which a reclaim was measured. That is the original failure on the common
    path for a Python change, not a tail case, and the PR text had argued it
    was a tail case on the strength of the Markdown path spawning one child.

    Asserts the aggregate, which is the property that was missing: every child
    sees a deadline drawn from a total no larger than the container ceiling, so
    the sum cannot exceed it however many commands there are.

    Caught in review on PR #5319.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(
        git_hook_policy,
        "_container_clamped",
        lambda seconds: min(seconds, git_hook_policy.CONTAINER_SUBPROCESS_CEILING_SECONDS),
    )
    seen: list[float] = []

    def fake_run_command(args: Any, repo_root: Any, **kwargs: Any):
        seen.append(kwargs["timeout_seconds"])
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda result: None)

    assert git_hook_policy.run_pytest(tmp_path) == 0
    assert len(seen) > 1, (
        "this test needs a multi-command set to say anything; the opt-in path "
        "should emit the executing partitions."
    )
    ceiling = git_hook_policy.CONTAINER_SUBPROCESS_CEILING_SECONDS
    assert seen[0] <= ceiling, (
        f"the first child got {seen[0]}s against a {ceiling}s container "
        "ceiling, so the aggregate was not clamped and the step can outlive "
        "the container across several children."
    )


_NARROWED_TO_EVERY_PARTITION = Selection(
    full=False,
    tests=(
        "tests/test_leaf.py",
        "tests/mutation/test_thing.py",
        "tests/test_safe_push_pr_branch.py",
        "tests/test_pr_autofix_late_live_state_gate.py",
    ),
    reason="narrowed",
)


def _run_pytest_on_a_narrowed_subset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, clamp: Any
) -> list[float]:
    """Drive the ordinary import-graph path and return each child's deadline."""
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(
        git_hook_policy.select_tests, "changed_from_git", lambda *_a, **_k: ["scripts/x.py"]
    )
    monkeypatch.setattr(
        git_hook_policy.select_tests, "select", lambda *_a, **_k: _NARROWED_TO_EVERY_PARTITION
    )
    monkeypatch.setattr(git_hook_policy, "_container_clamped", clamp)
    seen: list[float] = []

    def fake_run_command(args: Any, repo_root: Any, **kwargs: Any):
        seen.append(kwargs["timeout_seconds"])
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda result: None)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    return seen


def test_the_ordinary_subset_path_takes_the_execution_budget_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Why the aggregate clamp is not only about the opt-in.

    Every budget test in this section forces
    `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`, because that is the reliable way
    to make `run_pytest` build more than one command. Review on PR #5319
    pointed out what that leaves untested: a narrowed import-graph selection
    also emits up to four partition commands, and `_pytest_budget_seconds`
    gives any multi-command set the execution budget. So the 780s figure the
    PR text described as an opt-in property is what an everyday Python push
    takes, and nothing said so.

    This is the workstation half. The container half is the test below, and
    the pair is the point: the same path, clamped and unclamped, is what makes
    the clamp's effect visible rather than asserted.
    """
    seen = _run_pytest_on_a_narrowed_subset(monkeypatch, tmp_path, clamp=lambda seconds: seconds)

    assert len(seen) > 1, (
        "the narrowed selection did not emit multiple partition commands, so "
        "this test and the one below say nothing about a shared budget."
    )
    assert seen[0] == pytest.approx(git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS), (
        f"the ordinary subset path got {seen[0]}s. It takes the execution "
        "budget, not the collection budget, which is exactly why the container "
        "clamp below has to cover it."
    )


def test_a_container_bounds_the_ordinary_subset_path_as_well(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same path as above, inside a container.

    Without the aggregate clamp this is four children at the 150s child
    ceiling, roughly 600s against the ~679s at which a reclaim was measured,
    on the path a Python change takes. The test above establishes that the
    budget really is the execution one here, so a pass on this test is about
    the clamp rather than about the path being cheap.
    """
    ceiling = git_hook_policy.CONTAINER_SUBPROCESS_CEILING_SECONDS
    seen = _run_pytest_on_a_narrowed_subset(
        monkeypatch, tmp_path, clamp=lambda seconds: min(seconds, ceiling)
    )

    assert len(seen) > 1
    assert seen[0] <= ceiling, (
        f"the first child of a narrowed subset got {seen[0]}s against a "
        f"{ceiling}s container ceiling. The aggregate is unclamped on this "
        "path, so the step can outlive the container across its partitions."
    )


def test_run_pytest_budget_exhaustion_emits_exhaustion_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Positive: when a command times out with a small remaining budget, the
    message names the total budget and labels the event as exhaustion.

    Without the fix, _timeout_message reports only the 10.56-second remainder,
    reading like a hung test.  With the fix, stderr also contains an
    exhaustion clarification naming the full budget.
    """
    # Suite-budget semantics live on the executing partition set; the
    # default pre-push path builds one collection command (ADR-104).
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(git_hook_policy, "_container_clamped", lambda seconds: seconds)
    budget = git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    # Use almost all the budget for the first command, leaving 10s for the
    # second.  Simulate the second command timing out (returncode 3).
    clock = {"now": 1_000.0}

    def fake_monotonic() -> float:
        return clock["now"]

    call_count = {"n": 0}

    def fake_run_command(
        args: Any,
        repo_root: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        call_count["n"] += 1
        remaining = kwargs["timeout_seconds"]
        if call_count["n"] == 1:
            # First command consumes nearly all budget.
            clock["now"] += budget - 10.0
            return subprocess.CompletedProcess(list(args), 0, "", "")
        # Second command: started with ~10s left; simulate timeout.
        clock["now"] += remaining + 1
        timeout_msg = f"ERROR: python3 -m pytest timed out after {remaining:g} seconds\n"
        return subprocess.CompletedProcess(list(args), 3, "", timeout_msg)

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda r: None)

    rc = git_hook_policy.run_pytest(tmp_path)

    assert rc == 3
    err = capsys.readouterr().err
    assert "budget exhaustion" in err.lower() or "exhausted" in err.lower()
    assert str(budget) in err


def test_run_pytest_full_timeout_does_not_emit_exhaustion_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative: when the first command uses the full budget, no exhaustion
    message is emitted for it.  The generic timeout message is the right signal.
    """
    # Suite-budget semantics live on the executing partition set; the
    # default pre-push path builds one collection command (ADR-104).
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    budget = git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    clock = {"now": 1_000.0}

    def fake_monotonic() -> float:
        return clock["now"]

    def fake_run_command(
        args: Any,
        repo_root: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        clock["now"] += budget + 1
        timeout_msg = f"ERROR: python3 -m pytest timed out after {budget:g} seconds\n"
        return subprocess.CompletedProcess(list(args), 3, "", timeout_msg)

    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(git_hook_policy, "_run_command", fake_run_command)
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda r: None)

    rc = git_hook_policy.run_pytest(tmp_path)

    assert rc == 3
    err = capsys.readouterr().err
    # The exhaustion clarification must NOT fire when the first command
    # used the full budget (remaining == budget at call time).
    assert "budget exhaustion" not in err.lower()
    assert "exhausted" not in err.lower()
    # The helper opts into local execution, which announces itself. That line
    # is a selection notice, not a diagnostic about the budget, so it must not
    # be what satisfies the two assertions above. The wording moved when the
    # opt-in was hoisted ahead of selection on PR #5319: the notice is now
    # emitted by `_resolve_pytest_commands` rather than by the stand-in, so it
    # names the variable and says the graph was skipped.
    assert "executing the whole suite locally" in err
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV in err


def test_run_pytest_budget_exhaustion_cosmetic_change_survives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Inverted control: a cosmetic edit to the success message must not
    change the exit code.

    An earlier docstring claimed a mutation harness consumes this test.
    `git grep -nF cosmetic_change_survives` returns only this definition and
    nothing under `tests/mutation/` references it, so that claim is dropped
    rather than repeated. The test earns its place on its own terms: it is the
    one assertion here that must survive a wording mutation.
    """
    _record_pytest_timeouts(monkeypatch, elapsed_per_command=1.0)
    rc = git_hook_policy.run_pytest(tmp_path)
    assert rc == 0
    # Deliberately tolerant. This is an inverted control: it must SURVIVE a
    # cosmetic edit to the success path's wording, or it cannot distinguish
    # "every mutant died" from "this harness fails no matter what". An earlier
    # revision asserted the exact stderr line and died to a single added space,
    # which inverted the control's polarity. The exact-text assertion belongs
    # in its own test, below, where dying to a wording change is correct.
    err = capsys.readouterr().err
    assert "ERROR" not in err
    assert "timed out" not in err


def test_the_clean_opt_in_run_prints_only_the_selection_notice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing else may reach stderr on the success path.

    Separate from the control above on purpose: this one SHOULD fail if the
    notice's wording changes, because a new diagnostic appearing on a clean
    run is exactly what it is here to notice.
    """
    _record_pytest_timeouts(monkeypatch, elapsed_per_command=1.0)
    assert git_hook_policy.run_pytest(tmp_path) == 0
    # One line, and it no longer mentions the diff: the opt-in short-circuits
    # ahead of selection on PR #5319, so nothing consults the import graph and
    # the notice cannot report a reason for falling back to the whole suite.
    assert capsys.readouterr().err.splitlines() == [
        f"{git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV}=1: executing the "
        "whole suite locally, skipping import-graph selection."
    ]


# The #4293 pre-push guard must not reject this script's own lease push
# ---------------------------------------------------------------------------

_PRE_PUSH_HOOK = """#!/bin/sh
exec {interpreter} "$0.py"
"""

_PRE_PUSH_HOOK_PY = """
import sys
from pathlib import Path

sys.path.insert(0, {repo_root!r})
from scripts.validation import git_hook_policy

refs = git_hook_policy.parse_push_refs(sys.stdin)
codes = [
    git_hook_policy._check_non_fast_forward(ref, Path({work!r})) for ref in refs
]
sys.exit(1 if any(codes) else 0)
"""


def _install_non_fast_forward_hook(repo: Path) -> None:
    """Install the real #4293 guard as this repo's pre-push hook.

    Drives ``_check_non_fast_forward`` over the argv-free stdin git hands a
    pre-push hook, which is the only channel the guard reads. A push that
    rewrites published history exits 1 here whatever flags git was given.
    """
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    hook.write_text(
        _PRE_PUSH_HOOK.format(interpreter=shlex.quote(sys.executable)),
        encoding="utf-8",
    )
    (hooks / "pre-push.py").write_text(
        _PRE_PUSH_HOOK_PY.format(
            repo_root=str(Path(__file__).resolve().parents[1]),
            work=str(repo),
        ),
        encoding="utf-8",
    )
    hook.chmod(0o755)


def _rewritten_branch_with_lease(tmp_path: Path) -> tuple[Path, str]:
    """Return (repo, expected_remote_sha) with local history rewritten."""
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(repo))
    expected_sha = _bare_git(bare, "rev-parse", "refs/heads/feature-x")
    _commit_file(repo, "next.txt", "next\n")
    safe_push("feature-x", "origin", str(repo))
    expected_sha = _bare_git(bare, "rev-parse", "refs/heads/feature-x")

    _git(repo, "reset", "--hard", "HEAD~1")
    _commit_file(repo, "rewrite.txt", "rewrite\n")
    return repo, expected_sha


def test_lease_push_survives_the_non_fast_forward_pre_push_guard(tmp_path: Path) -> None:
    repo, expected_sha = _rewritten_branch_with_lease(tmp_path)
    _install_non_fast_forward_hook(repo)

    audit = safe_push(
        "feature-x",
        "origin",
        str(repo),
        expected_remote_sha=expected_sha,
        force_with_lease=True,
    )

    assert audit.verified is True


def test_the_same_rewrite_without_a_lease_is_blocked_by_the_guard(tmp_path: Path) -> None:
    repo, _ = _rewritten_branch_with_lease(tmp_path)
    _install_non_fast_forward_hook(repo)

    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))

    assert excinfo.value.exit_code == EXIT_TRANSPORT


def test_lease_push_sets_the_documented_escape_and_a_plain_push_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The escape is scoped to the lease push, not exported for every push."""
    seen: list[dict[str, str] | None] = []
    real_run_git = safe_push_pr_branch._run_git

    def record(args: list[str], repo_root: str, env: dict[str, str] | None = None):
        if args and args[0] == "push":
            seen.append(env)
        return real_run_git(args, repo_root, env)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", record)

    repo, expected_sha = _rewritten_branch_with_lease(tmp_path)
    safe_push(
        "feature-x",
        "origin",
        str(repo),
        expected_remote_sha=expected_sha,
        force_with_lease=True,
    )
    _commit_file(repo, "after.txt", "after\n")
    safe_push("feature-x", "origin", str(repo))

    lease_env, plain_env = seen[-2], seen[-1]
    assert lease_env is not None
    assert lease_env[safe_push_pr_branch.FORCE_PUSH_ESCAPE_ENV] == "1"
    assert plain_env is None
