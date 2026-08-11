"""CLI surface tests for new_pr.py: parser, main(), and repo discovery.

Split from the former single ``tests/test_new_pr.py`` (issue #4764), which had
grown to 1,390 lines and mixed unrelated responsibilities in one module. The
shared import of the script under test and the subprocess helpers live in
``tests/new_pr_harness.py`` so no module re-derives them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from tests.new_pr_harness import (
    SCRIPTS_DIR,
    build_parser,
    get_repo_root,
    main,
    validate_conventional_commit,
)
from tests.new_pr_harness import (
    completed as _completed,
)
from tests.new_pr_harness import (
    new_pr as _mod,
)

_SCRIPTS_DIR = SCRIPTS_DIR


class TestBuildParser:
    def test_title_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_valid_args(self):
        args = build_parser().parse_args(["--title", "feat: test", "--base", "main"])
        assert args.title == "feat: test"
        assert args.base == "main"

    def test_draft_flag(self):
        args = build_parser().parse_args(["--title", "fix: bug", "--draft"])
        assert args.draft is True

    def test_skip_validation_flag(self):
        args = build_parser().parse_args([
            "--title", "fix: bug", "--skip-validation", "--audit-reason", "emergency",
        ])
        assert args.skip_validation is True
        assert args.audit_reason == "emergency"


# ---------------------------------------------------------------------------
# Tests: validate_conventional_commit
# ---------------------------------------------------------------------------


class TestValidateConventionalCommit:
    def test_valid_feat(self):
        assert validate_conventional_commit("feat: add new feature") is True

    def test_valid_fix_with_scope(self):
        assert validate_conventional_commit("fix(auth): resolve login issue") is True

    def test_valid_breaking_change(self):
        assert validate_conventional_commit("feat!: breaking change") is True

    def test_invalid_format(self):
        assert validate_conventional_commit("Update something") is False

    def test_invalid_type(self):
        assert validate_conventional_commit("update: something") is False


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_gh_not_installed_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),  # git rev-parse
                _completed(rc=1),  # gh --version
            ],
        ):
            rc = main(["--title", "feat: test"])
        assert rc == 2

    def test_invalid_title_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
            ],
        ):
            rc = main(["--title", "Bad title format"])
        assert rc == 2

    def test_skip_validation_without_reason_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
            ],
        ):
            rc = main(["--title", "feat: test", "--skip-validation"])
        assert rc == 2

    def test_successful_pr_creation(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
                _completed(stdout="", rc=0),  # git diff (validations)
                _completed(stdout="{}", stderr="", rc=0),  # PR description validation
                _completed(rc=0),  # gh pr create
            ],
        ):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 0

    def test_body_file_not_found_returns_2(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse --show-toplevel
                _completed(rc=0),  # gh --version
                _completed(rc=0),  # git rev-parse --verify origin/main
            ],
        ), patch("new_pr.run_validations"):
            rc = main([
                "--title", "feat: test", "--head", "feat/branch",
                "--body-file", "/nonexistent/file.md",
            ])
        assert rc == 2

    def test_gh_pr_create_failure_returns_exit_code(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse --show-toplevel
                _completed(rc=0),  # gh --version
                _completed(rc=0),  # git rev-parse --verify origin/main
                _completed(rc=1, stderr="error creating PR"),  # gh pr create
            ],
        ), patch("new_pr.run_validations"):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 1

    def test_gh_pr_create_failure_keeps_stderr_when_output_redirected(self, tmp_path):
        marker = "GH_STUB_PR_CREATE_ERROR_MARKER"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gh_stub = bin_dir / "gh"
        gh_stub.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "if sys.argv[1:] == ['--version']:\n"
            "    print('gh version stub')\n"
            "    raise SystemExit(0)\n"
            "if sys.argv[1:3] == ['pr', 'create']:\n"
            f"    sys.stderr.write({marker!r} + '\\n')\n"
            "    sys.stderr.flush()\n"
            "    raise SystemExit(1)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8",
        )
        gh_stub.chmod(0o755)

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        body = tmp_path / "body.md"
        body.write_text("## Summary\n\nRegression test.\n", encoding="utf-8")
        log = tmp_path / "new-pr.log"
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
        env.pop("PYTHONUNBUFFERED", None)

        with log.open("wb") as stdout_log, log.open("r+b") as stderr_log:
            result = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPTS_DIR / "new_pr.py"),
                    "--title",
                    "fix: buffered failure output",
                    "--base",
                    "main",
                    "--head",
                    "feat/branch",
                    "--body-file",
                    str(body),
                    "--skip-validation",
                    "--audit-reason",
                    "redirected-output-regression-test",
                ],
                cwd=repo,
                env=env,
                stdout=stdout_log,
                stderr=stderr_log,
                timeout=30,
                check=False,
            )

        log_text = log.read_text(encoding="utf-8")
        assert result.returncode == 1
        assert marker in log_text
        assert "PR creation failed (exit code: 1)" in log_text

    def test_empty_branch_returns_2(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="", rc=0),  # git branch (empty)
            ],
        ):
            rc = main(["--title", "feat: test"])
        assert rc == 2

    def test_skip_validation_with_reason_writes_audit(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(rc=0),  # gh pr create
            ],
        ), patch("new_pr.write_audit_log") as mock_audit:
            rc = main([
                "--title", "feat: test",
                "--head", "feat/branch",
                "--skip-validation", "--audit-reason", "hotfix",
            ])
        assert rc == 0
        mock_audit.assert_called_once()
        call_args = mock_audit.call_args
        assert call_args[0][4] == "hotfix"

    def test_validation_exception_returns_1(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse --show-toplevel
                _completed(rc=0),  # gh --version
                _completed(rc=0),  # git rev-parse --verify origin/main
            ],
        ), patch(
            "new_pr.run_validations",
            side_effect=Exception("unexpected error"),
        ):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 1

    def test_body_file_used_when_provided(self, tmp_path):
        body_file = tmp_path / "body.md"
        body_file.write_text("PR body content")
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse --show-toplevel
                _completed(rc=0),  # gh --version
                _completed(rc=0),  # git rev-parse --verify origin/main
                _completed(stdout="", rc=0),  # git diff (validations)
                _completed(stdout="{}", stderr="", rc=0),  # PR description validation
                _completed(rc=0),  # gh pr create
            ],
        ):
            rc = main([
                "--title", "feat: test", "--head", "feat/branch",
                "--body-file", str(body_file),
            ])
        assert rc == 0

    def test_draft_flag_passed(self, tmp_path):
        calls = []

        def _side_effect(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args", []))
            if len(calls) == 1:
                return _completed(stdout=str(tmp_path), rc=0)  # git rev-parse
            if len(calls) == 2:
                return _completed(rc=0)  # gh --version
            if len(calls) == 3:
                return _completed(stdout="", rc=0)  # git diff
            if len(calls) == 4:
                return _completed(stdout="{}", stderr="", rc=0)  # PR description validation
            return _completed(rc=0)  # gh pr create

        with patch("subprocess.run", side_effect=_side_effect):
            rc = main([
                "--title", "feat: test", "--head", "feat/branch", "--draft",
            ])
        assert rc == 0
        gh_pr_create_args = calls[-1]
        assert "--draft" in gh_pr_create_args


# ---------------------------------------------------------------------------
# Tests: get_repo_root
# ---------------------------------------------------------------------------


class TestGetRepoRoot:
    def test_not_in_git_repo_exits_2(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=128, stderr="not a git repository"),
        ):
            with pytest.raises(SystemExit) as exc:
                get_repo_root()
            assert exc.value.code == 2

    def test_returns_repo_root(self):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="/home/user/repo\n", rc=0),
        ):
            assert get_repo_root() == "/home/user/repo"

    def test_uses_show_toplevel(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = _completed(stdout="/home/user/repo\n", rc=0)
            get_repo_root()
            assert mock_run.call_args.args[0] == [
                "git",
                "rev-parse",
                "--show-toplevel",
            ]

    def test_git_env_strips_hook_overrides(self, monkeypatch):
        monkeypatch.setenv("GIT_DIR", "/wrong/git")
        monkeypatch.setenv("GIT_WORK_TREE", "/wrong/worktree")
        monkeypatch.setenv("GIT_COMMON_DIR", "/wrong/common")
        monkeypatch.setenv("GIT_INDEX_FILE", "/wrong/index")
        env = _mod._git_env()
        assert "GIT_DIR" not in env
        assert "GIT_WORK_TREE" not in env
        assert "GIT_COMMON_DIR" not in env
        assert "GIT_INDEX_FILE" not in env

    def test_returns_worktree_top_not_main_checkout(self):
        """In a linked worktree, repo root is the worktree top (#2387)."""
        worktree_top = "/repo/.git/worktrees/feat/checkout"
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=worktree_top + "\n", rc=0),
        ):
            assert get_repo_root() == worktree_top


# ---------------------------------------------------------------------------
# Tests: run_validations
# ---------------------------------------------------------------------------
