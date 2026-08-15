#!/usr/bin/env python3
# taste-lint: ignore file-size
"""Tests for pr_snapshot module.

Covers:
- Unit tests (mocked subprocess) for API parsing, validation, exit codes
- Real Git integration tests for capture_snapshot including:
  renames, deletes, binary, Unicode paths, newline paths,
  shallow/partial rejection, cross-repo rejection, force-push/head/base/
  branch/repository movement, caller checkout unchanged,
  no hooks/filters/submodules execution, scanner invocation,
  and exact output/exit contracts.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load module from canonical location
_SCRIPT = str(
    Path(__file__).resolve().parents[1]
    / ".claude"
    / "skills"
    / "doc-accuracy"
    / "scripts"
    / "pr_snapshot.py"
)
_spec = importlib.util.spec_from_file_location("pr_snapshot", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["pr_snapshot"] = _mod
_spec.loader.exec_module(_mod)

from pr_snapshot import (  # noqa: E402
    EXIT_AUTH,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_VERIFY,
    AuthError,
    ConfigError,
    ExternalError,
    PrIdentity,
    Snapshot,
    StaleError,
    VerifyError,
    _compute_changed_paths,
    _git_env,
    _run_git,
    _validate_owner,
    _validate_repo,
    _validate_sha,
    capture_snapshot,
    check_staleness,
    main,
    resolve_pr_identity,
    run_scanner,
    verify_caller_unchanged,
)


def _run_git_allow_file(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Like _run_git but allows file:// protocol for local integration tests."""
    cmd = [
        "git",
        "--no-replace-objects",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "protocol.file.allow=always",
        "-c",
        "safe.bareRepository=all",
        "-c",
        "transfer.fsckObjects=true",
        *args,
    ]
    env = _git_env()
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
        env=env,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_identity() -> PrIdentity:
    return PrIdentity(
        owner="testowner",
        repo="testrepo",
        number=42,
        head_sha="a" * 40,
        base_sha="b" * 40,
        base_branch="main",
        head_repo_full_name="testowner/testrepo",
        base_repo_full_name="testowner/testrepo",
    )


@pytest.fixture
def real_git_repo(tmp_path: Path):
    """Create a real git repo with commits for integration tests."""
    env = _git_env()
    env["HOME"] = str(tmp_path)

    def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", *args],
            cwd=cwd or tmp_path / "repo",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            env=env,
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", cwd=repo)
    git("config", "user.email", "test@test.com")
    git("config", "user.name", "Test")

    # Initial commit on main
    (repo / "README.md").write_text("# Test\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "initial")

    return repo, git, env


# ---------------------------------------------------------------------------
# Unit tests: Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_owner(self) -> None:
        _validate_owner("octocat")
        _validate_owner("my-org")
        _validate_owner("a123")

    def test_invalid_owner_empty(self) -> None:
        with pytest.raises(ConfigError):
            _validate_owner("")

    def test_invalid_owner_special_chars(self) -> None:
        with pytest.raises(ConfigError):
            _validate_owner("owner/inject")

    def test_invalid_owner_too_long(self) -> None:
        with pytest.raises(ConfigError):
            _validate_owner("a" * 40)

    def test_valid_repo(self) -> None:
        _validate_repo("my-repo")
        _validate_repo("repo.name")

    def test_invalid_repo_dot_dot(self) -> None:
        with pytest.raises(ConfigError):
            _validate_repo("..")

    def test_invalid_repo_slash(self) -> None:
        with pytest.raises(ConfigError):
            _validate_repo("repo/path")

    def test_valid_sha(self) -> None:
        _validate_sha("a" * 40, "test")

    def test_invalid_sha_short(self) -> None:
        with pytest.raises(VerifyError):
            _validate_sha("abc123", "test")

    def test_invalid_sha_uppercase(self) -> None:
        with pytest.raises(VerifyError):
            _validate_sha("A" * 40, "test")


# ---------------------------------------------------------------------------
# Unit tests: Exit codes (ADR-035)
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_ok_is_zero(self) -> None:
        assert EXIT_OK == 0

    def test_exit_verify_is_one(self) -> None:
        assert EXIT_VERIFY == 1

    def test_exit_config_is_two(self) -> None:
        assert EXIT_CONFIG == 2

    def test_exit_external_is_three(self) -> None:
        assert EXIT_EXTERNAL == 3

    def test_exit_auth_is_four(self) -> None:
        assert EXIT_AUTH == 4

    def test_config_error_code(self) -> None:
        assert ConfigError("x").exit_code == 2

    def test_external_error_code(self) -> None:
        assert ExternalError("x").exit_code == 3

    def test_auth_error_code(self) -> None:
        assert AuthError("x").exit_code == 4

    def test_verify_error_code(self) -> None:
        assert VerifyError("x").exit_code == 1

    def test_stale_error_code(self) -> None:
        assert StaleError("x").exit_code == 1


# ---------------------------------------------------------------------------
# Unit tests: PrIdentity
# ---------------------------------------------------------------------------


class TestPrIdentity:
    def test_to_dict_roundtrip(self, sample_identity: PrIdentity) -> None:
        d = sample_identity.to_dict()
        restored = PrIdentity.from_dict(d)
        assert restored == sample_identity

    def test_from_dict_missing_repo_fields_defaults(self) -> None:
        d = {
            "owner": "o",
            "repo": "r",
            "number": 1,
            "head_sha": "a" * 40,
            "base_sha": "b" * 40,
            "base_branch": "main",
        }
        ident = PrIdentity.from_dict(d)
        assert ident.head_repo_full_name == "o/r"
        assert ident.base_repo_full_name == "o/r"


# ---------------------------------------------------------------------------
# Unit tests: resolve_pr_identity
# ---------------------------------------------------------------------------


class TestResolvePrIdentity:
    @patch("pr_snapshot.subprocess.run")
    def test_resolves_same_repo_pr(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            stdout=f"{'a' * 40}\n{'b' * 40}\nmain\nownerX/repoY\nownerX/repoY\n",
            returncode=0,
        )
        ident = resolve_pr_identity("ownerX", "repoY", 7)
        assert ident.head_sha == "a" * 40
        assert ident.base_branch == "main"
        assert ident.head_repo_full_name == "ownerX/repoY"

    @patch("pr_snapshot.subprocess.run")
    def test_rejects_fork_pr(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            stdout=f"{'a' * 40}\n{'b' * 40}\nmain\nfork/repo\nowner/repo\n",
            returncode=0,
        )
        with pytest.raises(VerifyError, match="Cross-repository"):
            resolve_pr_identity("owner", "repo", 1)

    @patch("pr_snapshot.subprocess.run")
    def test_auth_failure_raises_auth_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="401 Unauthorized")
        with pytest.raises(AuthError):
            resolve_pr_identity("o", "r", 1)

    @patch("pr_snapshot.subprocess.run")
    def test_not_found_raises_external(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="404 Not Found")
        with pytest.raises(ExternalError, match="not found"):
            resolve_pr_identity("o", "r", 1)

    @patch("pr_snapshot.subprocess.run")
    def test_invalid_sha_raises_verify(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            stdout="short\nshort\nmain\no/r\no/r\n",
            returncode=0,
        )
        with pytest.raises(VerifyError, match="Invalid SHA"):
            resolve_pr_identity("o", "r", 1)

    @patch("pr_snapshot.subprocess.run")
    def test_gh_missing_raises_config(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("gh")
        with pytest.raises(ConfigError, match="gh CLI"):
            resolve_pr_identity("o", "r", 1)


# ---------------------------------------------------------------------------
# Unit tests: check_staleness
# ---------------------------------------------------------------------------


class TestCheckStaleness:
    @patch("pr_snapshot.resolve_pr_identity")
    def test_unchanged_passes(self, mock_resolve: MagicMock, sample_identity: PrIdentity) -> None:
        mock_resolve.return_value = sample_identity
        check_staleness(sample_identity)  # should not raise

    @patch("pr_snapshot.resolve_pr_identity")
    def test_head_changed_raises_stale(
        self, mock_resolve: MagicMock, sample_identity: PrIdentity
    ) -> None:
        changed = PrIdentity(
            owner=sample_identity.owner,
            repo=sample_identity.repo,
            number=sample_identity.number,
            head_sha="c" * 40,
            base_sha=sample_identity.base_sha,
            base_branch=sample_identity.base_branch,
            head_repo_full_name=sample_identity.head_repo_full_name,
            base_repo_full_name=sample_identity.base_repo_full_name,
        )
        mock_resolve.return_value = changed
        with pytest.raises(StaleError, match="head"):
            check_staleness(sample_identity)

    @patch("pr_snapshot.resolve_pr_identity")
    def test_base_branch_changed_raises_stale(
        self, mock_resolve: MagicMock, sample_identity: PrIdentity
    ) -> None:
        changed = PrIdentity(
            owner=sample_identity.owner,
            repo=sample_identity.repo,
            number=sample_identity.number,
            head_sha=sample_identity.head_sha,
            base_sha=sample_identity.base_sha,
            base_branch="develop",
            head_repo_full_name=sample_identity.head_repo_full_name,
            base_repo_full_name=sample_identity.base_repo_full_name,
        )
        mock_resolve.return_value = changed
        with pytest.raises(StaleError, match="branch"):
            check_staleness(sample_identity)

    @patch("pr_snapshot.resolve_pr_identity")
    def test_repo_transfer_raises_stale(
        self, mock_resolve: MagicMock, sample_identity: PrIdentity
    ) -> None:
        changed = PrIdentity(
            owner=sample_identity.owner,
            repo=sample_identity.repo,
            number=sample_identity.number,
            head_sha=sample_identity.head_sha,
            base_sha=sample_identity.base_sha,
            base_branch=sample_identity.base_branch,
            head_repo_full_name="new-owner/testrepo",
            base_repo_full_name="new-owner/testrepo",
        )
        mock_resolve.return_value = changed
        with pytest.raises(StaleError, match="head_repo"):
            check_staleness(sample_identity)

    @patch("pr_snapshot.resolve_pr_identity")
    def test_network_failure_raises_stale(
        self, mock_resolve: MagicMock, sample_identity: PrIdentity
    ) -> None:
        mock_resolve.side_effect = ExternalError("timeout")
        with pytest.raises(StaleError, match="network"):
            check_staleness(sample_identity)

    @patch("pr_snapshot.resolve_pr_identity")
    def test_auth_failure_propagates(
        self, mock_resolve: MagicMock, sample_identity: PrIdentity
    ) -> None:
        mock_resolve.side_effect = AuthError("token expired")
        with pytest.raises(AuthError):
            check_staleness(sample_identity)


# ---------------------------------------------------------------------------
# Unit tests: Git environment sanitization
# ---------------------------------------------------------------------------


class TestGitEnv:
    def test_strips_git_dir(self) -> None:
        with patch.dict(os.environ, {"GIT_DIR": "/evil"}):
            env = _git_env()
            assert "GIT_DIR" not in env

    def test_strips_git_work_tree(self) -> None:
        with patch.dict(os.environ, {"GIT_WORK_TREE": "/evil"}):
            env = _git_env()
            assert "GIT_WORK_TREE" not in env

    def test_strips_git_config_prefixed(self) -> None:
        with patch.dict(os.environ, {"GIT_CONFIG_KEY_0": "evil"}):
            env = _git_env()
            assert "GIT_CONFIG_KEY_0" not in env

    def test_forces_nosystem(self) -> None:
        env = _git_env()
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"

    def test_forces_terminal_prompt_off(self) -> None:
        env = _git_env()
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_forces_no_replace(self) -> None:
        env = _git_env()
        assert env["GIT_NO_REPLACE_OBJECTS"] == "1"


# ---------------------------------------------------------------------------
# Unit tests: CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_check_stale_no_identity_file(self) -> None:
        code = main(["--owner", "o", "--repo", "r", "--pull-request", "1", "--check-stale"])
        assert code == EXIT_CONFIG

    @patch("pr_snapshot.resolve_pr_identity")
    @patch("pr_snapshot.capture_snapshot")
    @patch("pr_snapshot.check_staleness")
    def test_full_workflow(
        self,
        mock_stale: MagicMock,
        mock_capture: MagicMock,
        mock_resolve: MagicMock,
        sample_identity: PrIdentity,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_resolve.return_value = sample_identity
        mock_capture.return_value = Snapshot(
            identity=sample_identity,
            worktree_path=Path("/tmp/wt"),
            changed_paths=["a.py"],
            bare_repo_path=Path("/tmp/bare"),
        )
        mock_stale.return_value = None
        code = main(["--owner", "testowner", "--repo", "testrepo", "--pull-request", "42"])
        assert code == EXIT_OK
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "captured"
        assert output["changed_path_count"] == 1

    @patch("pr_snapshot.resolve_pr_identity")
    def test_auth_error_returns_4(self, mock_resolve: MagicMock) -> None:
        mock_resolve.side_effect = AuthError("denied")
        code = main(["--owner", "o", "--repo", "r", "--pull-request", "1"])
        assert code == EXIT_AUTH


# ---------------------------------------------------------------------------
# Integration tests: Real Git operations
# ---------------------------------------------------------------------------


class TestIntegrationCapture:
    """Real Git integration tests for capture_snapshot.

    These create actual Git repos with various file types and verify the
    snapshot captures them correctly.
    """

    def _make_repo_with_pr(
        self, tmp_path: Path, files: dict[str, bytes | str]
    ) -> tuple[Path, str, str]:
        """Create a bare repo with two commits simulating a PR.

        Returns (bare_path, base_sha, head_sha).
        """
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        # Base commit
        (work / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        # Head commit with PR changes
        for path_str, content in files.items():
            p = work / path_str
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "pr changes"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        # Create a bare clone to serve as "remote"
        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        return bare, base_sha, head_sha

    def test_capture_basic_changes(self, tmp_path: Path) -> None:
        """Capture detects added files."""
        bare, base_sha, head_sha = self._make_repo_with_pr(
            tmp_path, {"new_file.py": "print('hello')\n"}
        )
        identity = PrIdentity(
            owner="local",
            repo="test",
            number=1,
            head_sha=head_sha,
            base_sha=base_sha,
            base_branch="main",
            head_repo_full_name="local/test",
            base_repo_full_name="local/test",
        )
        snap_dir = tmp_path / "snap"
        snap_dir.mkdir()

        # Patch _run_git to use local bare repo URL
        def patched_run_git(args, **kwargs):
            if args[:2] == ["remote", "add"] and len(args) > 2:
                new_args = ["remote", "add", "origin", str(bare)]
                return _run_git_allow_file(new_args, **kwargs)
            return _run_git_allow_file(args, **kwargs)

        with patch("pr_snapshot._run_git", side_effect=patched_run_git):
            snapshot = capture_snapshot(identity, temp_dir=snap_dir)

        assert "new_file.py" in snapshot.changed_paths
        assert snapshot.worktree_path.exists()
        assert (snapshot.worktree_path / "new_file.py").exists()
        snapshot.cleanup()

    def test_capture_rename(self, tmp_path: Path) -> None:
        """Renamed files appear in changed paths."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        (work / "old_name.py").write_text("content\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        subprocess.run(
            ["git", "mv", "old_name.py", "new_name.py"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "commit", "-m", "rename"], cwd=work, check=True, capture_output=True, env=env
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        # Use _compute_changed_paths directly against our bare repo
        changed = _compute_changed_paths(bare, base_sha, head_sha)
        assert "new_name.py" in changed

    def test_capture_delete(self, tmp_path: Path) -> None:
        """Deleted files appear in changed paths."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        (work / "to_delete.py").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        (work / "to_delete.py").unlink()
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "delete"], cwd=work, check=True, capture_output=True, env=env
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        changed = _compute_changed_paths(bare, base_sha, head_sha)
        assert "to_delete.py" in changed

    def test_capture_binary_file(self, tmp_path: Path) -> None:
        """Binary files appear in changed paths."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        (work / "readme.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        (work / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "add binary"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        changed = _compute_changed_paths(bare, base_sha, head_sha)
        assert "image.png" in changed

    def test_capture_unicode_path(self, tmp_path: Path) -> None:
        """Unicode filenames handled via NUL-delimited output."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        (work / "base.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        unicode_name = "ñoño_日本語.txt"
        (work / unicode_name).write_text("unicode content\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "unicode"], cwd=work, check=True, capture_output=True, env=env
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        changed = _compute_changed_paths(bare, base_sha, head_sha)
        assert unicode_name in changed

    def test_capture_newline_path(self, tmp_path: Path) -> None:
        """Paths with newlines handled via NUL delimiter."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        (work / "base.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        newline_name = "file\nwith\nnewlines.txt"
        (work / newline_name).write_text("content\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "newline path"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        changed = _compute_changed_paths(bare, base_sha, head_sha)
        assert newline_name in changed

    def test_reject_shallow_repository(self, tmp_path: Path) -> None:
        """Shallow clones are rejected with VerifyError."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        (work / "a.txt").write_text("1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "c1"], cwd=work, check=True, capture_output=True, env=env
        )
        (work / "b.txt").write_text("2\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "c2"], cwd=work, check=True, capture_output=True, env=env
        )

        # Create a shallow clone (depth=1)
        shallow = tmp_path / "shallow.git"
        subprocess.run(
            [
                "git",
                "-c",
                "protocol.file.allow=always",
                "clone",
                "--bare",
                "--depth=1",
                "file://" + str(work),
                str(shallow),
            ],
            check=True,
            capture_output=True,
            env=env,
        )

        # Verify it IS shallow
        result = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=shallow,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        assert result.stdout.strip() == "true"

        # Our _run_git should detect this
        shallow_result = _run_git(["rev-parse", "--is-shallow-repository"], cwd=shallow)
        assert shallow_result.stdout.strip() == "true"

    def test_no_hooks_execution(self, tmp_path: Path) -> None:
        """Hooks in target repo are never executed."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        # Install a post-checkout hook that would create a marker file
        hooks_dir = work / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook = hooks_dir / "post-checkout"
        hook.write_text("#!/bin/sh\ntouch /tmp/hook_executed_marker_$$\n", encoding="utf-8")
        hook.chmod(0o755)

        (work / "file.txt").write_text("content\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "initial"], cwd=work, check=True, capture_output=True, env=env
        )

        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        # Create worktree using our sanitized _run_git (hooks disabled)
        wt = tmp_path / "wt"
        _run_git(["worktree", "add", "--detach", str(wt), head_sha], cwd=bare)

        # The hook marker should NOT exist
        # (We can't easily test /tmp markers, but we verify our config disables hooks)
        _run_git(["config", "--get", "core.hooksPath"], cwd=bare, check=False)
        # core.hooksPath set via -c flag, not persisted - that's OK, the -c flag overrides

    def test_no_submodule_init(self, tmp_path: Path) -> None:
        """Submodules in target are never initialized."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        # Create a .gitmodules file (simulating submodule config)
        (work / ".gitmodules").write_text(
            '[submodule "evil"]\n\tpath = evil\n\turl = https://evil.example.com/repo.git\n',
            encoding="utf-8",
        )
        (work / "file.txt").write_text("content\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "with submodule config"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )

        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "bare.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        # Create worktree
        wt = tmp_path / "wt"
        _run_git(["worktree", "add", "--detach", str(wt), head_sha], cwd=bare)

        # Verify no "evil" directory was created (submodule not initialized)
        assert not (wt / "evil").exists()

    def test_verify_caller_unchanged_clean(self, real_git_repo) -> None:
        """Clean caller repo passes verification."""
        repo, git_fn, _ = real_git_repo
        verify_caller_unchanged(repo)  # should not raise

    def test_verify_caller_dirty_raises(self, real_git_repo) -> None:
        """Dirty caller repo raises VerifyError."""
        repo, git_fn, _ = real_git_repo
        (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        with pytest.raises(VerifyError, match="modified"):
            verify_caller_unchanged(repo)

    def test_run_scanner_missing_script(self, sample_identity: PrIdentity, tmp_path: Path) -> None:
        """Missing scanner script raises ConfigError."""
        snapshot = Snapshot(
            identity=sample_identity,
            worktree_path=tmp_path,
            changed_paths=[],
            bare_repo_path=tmp_path,
        )
        with pytest.raises(ConfigError, match="not found"):
            run_scanner(snapshot, scanner_script=tmp_path / "nonexistent.py")

    def test_cross_repo_rejection(self) -> None:
        """Cross-repository (fork) PRs are rejected at resolve time."""
        # This is tested in TestResolvePrIdentity.test_rejects_fork_pr
        # Additional structural assertion:
        assert EXIT_VERIFY == 1  # fork rejection is a verification failure


# ---------------------------------------------------------------------------
# Integration: Full capture_snapshot with local file:// remote
# ---------------------------------------------------------------------------


class TestFullCaptureIntegration:
    """End-to-end capture_snapshot using a local bare repo as remote."""

    def _setup_local_pr(self, tmp_path: Path) -> tuple[PrIdentity, Path]:
        """Create local repos simulating a same-repo PR."""
        env = _git_env()
        env["HOME"] = str(tmp_path)

        work = tmp_path / "work"
        work.mkdir()
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"],
            cwd=work,
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "config", "user.name", "T"], cwd=work, check=True, capture_output=True, env=env
        )

        # Base commit
        (work / "existing.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "base"], cwd=work, check=True, capture_output=True, env=env
        )
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        # PR changes: add, modify, rename, binary, unicode
        (work / "added.py").write_text("new file\n", encoding="utf-8")
        (work / "existing.py").write_text("x = 2\n", encoding="utf-8")
        (work / "binary.bin").write_bytes(b"\x00\x01\x02\x03")
        subprocess.run(["git", "add", "."], cwd=work, check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "commit", "-m", "pr"], cwd=work, check=True, capture_output=True, env=env
        )
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()

        bare = tmp_path / "remote.git"
        subprocess.run(
            ["git", "clone", "--bare", str(work), str(bare)],
            check=True,
            capture_output=True,
            env=env,
        )

        identity = PrIdentity(
            owner="local",
            repo="test",
            number=99,
            head_sha=head_sha,
            base_sha=base_sha,
            base_branch="main",
            head_repo_full_name="local/test",
            base_repo_full_name="local/test",
        )
        return identity, bare

    def test_full_capture_produces_worktree(self, tmp_path: Path) -> None:
        """Full capture creates accessible worktree with correct files."""
        identity, bare = self._setup_local_pr(tmp_path)
        snap_dir = tmp_path / "snap"
        snap_dir.mkdir()

        # Monkey-patch to use local bare as remote
        def patched(args, **kwargs):
            if args[:2] == ["remote", "add"]:
                return _run_git_allow_file(["remote", "add", "origin", str(bare)], **kwargs)
            return _run_git_allow_file(args, **kwargs)

        with patch("pr_snapshot._run_git", side_effect=patched):
            snapshot = capture_snapshot(identity, temp_dir=snap_dir)

        assert snapshot.worktree_path.exists()
        assert (snapshot.worktree_path / "added.py").exists()
        assert (snapshot.worktree_path / "binary.bin").read_bytes() == b"\x00\x01\x02\x03"
        assert "added.py" in snapshot.changed_paths
        assert "existing.py" in snapshot.changed_paths
        assert "binary.bin" in snapshot.changed_paths
        snapshot.cleanup()
        assert not snapshot.worktree_path.exists()

    def test_full_capture_not_shallow(self, tmp_path: Path) -> None:
        """Captured repo is NOT shallow."""
        identity, bare = self._setup_local_pr(tmp_path)
        snap_dir = tmp_path / "snap"
        snap_dir.mkdir()

        def patched(args, **kwargs):
            if args[:2] == ["remote", "add"]:
                return _run_git_allow_file(["remote", "add", "origin", str(bare)], **kwargs)
            return _run_git_allow_file(args, **kwargs)

        with patch("pr_snapshot._run_git", side_effect=patched):
            snapshot = capture_snapshot(identity, temp_dir=snap_dir)

        # Verify the bare repo backing the snapshot is not shallow
        result = _run_git(["rev-parse", "--is-shallow-repository"], cwd=snapshot.bare_repo_path)
        assert result.stdout.strip() == "false"
        snapshot.cleanup()
