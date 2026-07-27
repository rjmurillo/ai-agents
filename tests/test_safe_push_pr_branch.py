#!/usr/bin/env python3
"""Tests for ``.github/scripts/safe_push_pr_branch.py`` (issue #3412)."""

from __future__ import annotations

import builtins
import importlib.util
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "scripts"
    / "safe_push_pr_branch.py"
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
    stdout = (
        "To https://example/repo.git\n"
        " \tHEAD:refs/heads/foo\t1111111..2222222\n"
        "Done\n"
    )

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

    def fake_run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
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

    def fake_run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
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

    def fake_run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
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

    def fake_run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
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

    def fake_run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
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

    def fake_run_git(args: list[str], repo_root: str) -> subprocess.CompletedProcess[str]:
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


def test_pre_push_pytest_commands_include_safe_push_module() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    safe_push_tests = repo_root / "tests" / "test_safe_push_pr_branch.py"

    assert git_hook_policy._pytest_commands(repo_root) == [
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not integration",
            str(repo_root / "tests"),
            "--ignore",
            str(safe_push_tests),
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not safe_push_transport",
            str(safe_push_tests),
        ],
    ]
