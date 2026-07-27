#!/usr/bin/env python3
"""Tests for ``.github/scripts/safe_push_pr_branch.py`` (issue #3412).

Coverage matches the issue acceptance criteria:

- A push fails if the requested refspec is not present in the transport result
  (negative control via a forged porcelain result, and a wrong-branch guard).
- The push records requested refspec, local SHA, remote SHA, process id, and
  transport result (audit completeness).
- A regression with two linked worktrees and concurrent push activity proves
  each push updates only its own ref.
- The pre-push validation entrypoint never invokes ``git push``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

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
    # ``safe.bareRepository=explicit`` in a developer's global config blocks
    # cwd-based access to a bare repo; ``--git-dir`` is the explicit form.
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


# ---------------------------------------------------------------------------
# Unit: porcelain parsing and sha extraction
# ---------------------------------------------------------------------------


def test_parse_porcelain_maps_dest_ref_to_flag_and_summary() -> None:
    stdout = (
        "To https://example/repo.git\n"
        " \tHEAD:refs/heads/foo\t1111111..2222222\n"
        "Done\n"
    )
    refs = safe_push_pr_branch._parse_porcelain(stdout)
    assert refs["refs/heads/foo"] == (" ", "1111111..2222222")


def test_parse_porcelain_ignores_headers_and_blank_lines() -> None:
    refs = safe_push_pr_branch._parse_porcelain("To url\n\nDone\n")
    assert refs == {}


def test_extract_new_sha_parses_update_range() -> None:
    assert safe_push_pr_branch._extract_new_sha("1111111..2222222") == (
        "1111111",
        "2222222",
    )


def test_extract_new_sha_returns_none_for_new_branch() -> None:
    assert safe_push_pr_branch._extract_new_sha("[new branch]") == (None, None)


# ---------------------------------------------------------------------------
# Positive: real push to a bare remote verifies and audits
# ---------------------------------------------------------------------------


def test_push_updates_requested_ref_and_reports_verified(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    local_sha = _git(repo, "rev-parse", "HEAD")

    audit = safe_push("feature-x", "origin", str(repo))

    assert audit.verified is True
    assert audit.branch == "feature-x"
    assert audit.requested_refspec == "HEAD:refs/heads/feature-x"
    assert audit.local_sha == local_sha
    assert audit.process_id > 0
    assert audit.transport_text  # transport result recorded
    remote_sha = _bare_git(bare, "rev-parse", "refs/heads/feature-x")
    assert remote_sha == local_sha


def test_audit_records_remote_sha_on_update(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(repo))  # first push (new branch)

    (repo / "next.txt").write_text("next\n", encoding="utf-8")
    _git(repo, "add", "next.txt")
    _git(repo, "commit", "-qm", "second")
    local_sha = _git(repo, "rev-parse", "HEAD")

    audit = safe_push("feature-x", "origin", str(repo))

    assert audit.verified is True
    assert audit.remote_new_sha is not None
    # local_sha starts with the abbreviated new sha reported by porcelain.
    assert local_sha.startswith(audit.remote_new_sha)


# ---------------------------------------------------------------------------
# Negative control (criterion: fail if requested ref absent from transport)
# ---------------------------------------------------------------------------


def test_push_fails_when_transport_names_a_different_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "fix-3377")
    _git(repo, "remote", "add", "origin", str(bare))

    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(args: list[str], repo_root: str):
        if args and args[0] == "push":
            # Forge the issue #3412 signature: success exit, but the transport
            # line names an unrelated branch, not the requested one.
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=(
                    "To https://example/repo.git\n"
                    " \tHEAD:refs/heads/fix-3383\taaaaaaa..bbbbbbb\n"
                    "Done\n"
                ),
                stderr="",
            )
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    with pytest.raises(SafePushError) as excinfo:
        safe_push("fix-3377", "origin", str(repo))
    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert "absent from the transport result" in str(excinfo.value)


def test_push_fails_when_transport_sha_mismatches_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))

    real_run_git = safe_push_pr_branch._run_git

    def fake_run_git(args: list[str], repo_root: str):
        if args and args[0] == "push":
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=(
                    "To https://example/repo.git\n"
                    " \tHEAD:refs/heads/feature-x\t1111111..deadbee\n"
                    "Done\n"
                ),
                stderr="",
            )
        return real_run_git(args, repo_root)

    monkeypatch.setattr(safe_push_pr_branch, "_run_git", fake_run_git)

    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))
    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert "expected local sha" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Edge: wrong-branch and detached-HEAD guards refuse before pushing
# ---------------------------------------------------------------------------


def test_push_refuses_when_head_on_other_branch(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))

    with pytest.raises(SafePushError) as excinfo:
        safe_push("some-other-branch", "origin", str(repo))
    assert excinfo.value.exit_code == EXIT_VERIFICATION
    assert "HEAD is on" in str(excinfo.value)
    # Nothing was pushed.
    refs = _bare_git(bare, "for-each-ref", "--format=%(refname)")
    assert "some-other-branch" not in refs


def test_push_refuses_on_detached_head(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "checkout", "-q", "--detach")

    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))
    assert excinfo.value.exit_code == EXIT_VERIFICATION


def test_push_fails_on_non_fast_forward_rejection(tmp_path: Path) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))
    safe_push("feature-x", "origin", str(repo))

    # A second clone advances the remote so the first repo is now behind.
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(bare), str(other))
    _git(other, "config", "user.email", "t@e.com")
    _git(other, "config", "user.name", "T")
    _git(other, "checkout", "-q", "feature-x")
    (other / "adv.txt").write_text("adv\n", encoding="utf-8")
    _git(other, "add", "adv.txt")
    _git(other, "commit", "-qm", "advance")
    _git(other, "push", "-q", "origin", "feature-x")

    # The first repo makes a divergent commit and must be rejected, not silently
    # reported as success.
    (repo / "local.txt").write_text("local\n", encoding="utf-8")
    _git(repo, "add", "local.txt")
    _git(repo, "commit", "-qm", "divergent")
    with pytest.raises(SafePushError) as excinfo:
        safe_push("feature-x", "origin", str(repo))
    assert excinfo.value.exit_code in {EXIT_TRANSPORT, EXIT_VERIFICATION}


# ---------------------------------------------------------------------------
# Regression: two linked worktrees, concurrent push (criterion 4)
# ---------------------------------------------------------------------------


def test_concurrent_worktrees_each_push_only_their_own_ref(
    tmp_path: Path,
) -> None:
    bare = _bare_remote(tmp_path)

    # A base repo with two linked worktrees, each on its own branch, sharing one
    # object store. This mirrors the autofix matrix pushing several PR branches.
    base = tmp_path / "base"
    _init_worktree(base, "main")
    _git(base, "remote", "add", "origin", str(bare))
    wt_a = tmp_path / "wt-a"
    wt_b = tmp_path / "wt-b"
    _git(base, "worktree", "add", "-q", "-b", "fix-3377", str(wt_a))
    _git(base, "worktree", "add", "-q", "-b", "fix-3383", str(wt_b))
    for wt, tag in ((wt_a, "a"), (wt_b, "b")):
        (wt / f"{tag}.txt").write_text(f"{tag}\n", encoding="utf-8")
        _git(wt, "add", f"{tag}.txt")
        _git(wt, "commit", "-qm", f"work {tag}")

    # Values come from a runtime-loaded module, so ``Any`` is the honest static
    # type; the assertions below exercise the real PushAudit attributes.
    results: dict[str, Any] = {}
    errors: dict[str, Exception] = {}

    def _worker(wt: Path, branch: str) -> None:
        try:
            results[branch] = safe_push(branch, "origin", str(wt))
        except Exception as exc:  # noqa: BLE001 - recorded for assertion
            errors[branch] = exc

    threads = [
        threading.Thread(target=_worker, args=(wt_a, "fix-3377")),
        threading.Thread(target=_worker, args=(wt_b, "fix-3383")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors
    # Each branch on the remote points at its own worktree HEAD, never swapped.
    assert _bare_git(bare, "rev-parse", "refs/heads/fix-3377") == _git(
        wt_a, "rev-parse", "HEAD"
    )
    assert _bare_git(bare, "rev-parse", "refs/heads/fix-3383") == _git(
        wt_b, "rev-parse", "HEAD"
    )
    assert results["fix-3377"].branch == "fix-3377"
    assert results["fix-3383"].branch == "fix-3383"


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def test_main_rejects_flag_shaped_branch(capsys: pytest.CaptureFixture[str]) -> None:
    # ``--branch=--force`` keeps argparse from consuming ``--force`` as its own
    # option, so the flag-shaped value reaches main's guard.
    assert main(["--branch=--force", "--repo-root", "."]) == EXIT_USAGE


def test_main_success_emits_notice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bare = _bare_remote(tmp_path)
    repo = tmp_path / "work"
    _init_worktree(repo, "feature-x")
    _git(repo, "remote", "add", "origin", str(bare))

    code = main(["--branch", "feature-x", "--remote", "origin", "--repo-root", str(repo)])
    assert code == EXIT_OK
    captured = capsys.readouterr()
    assert "pushed feature-x" in captured.out
    # The audit JSON line went to stderr and carries the required fields.
    assert '"requested_refspec"' in captured.err
    assert '"process_id"' in captured.err
    assert '"local_sha"' in captured.err


# ---------------------------------------------------------------------------
# Criterion 2: the pre-push validation entrypoint never invokes ``git push``
# ---------------------------------------------------------------------------


def test_pre_push_policy_never_invokes_git_push() -> None:
    policy = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "validation"
        / "git_hook_policy.py"
    )
    source = policy.read_text(encoding="utf-8")
    # The pre-push gate must validate, never mutate a remote. A ``push``
    # subprocess token here would let the hook itself move refs.
    assert '"push"' not in source
    assert "'push'" not in source
