"""CLI orchestration tests for ``new_pr.py``."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from tests.new_pr_test_support import (
    _SCRIPTS_DIR,
    _completed,
    _mod,
    _prepared_body,
    build_parser,
    main,
    validate_conventional_commit,
)


class TestBuildParser:
    def test_missing_title_is_rejected_by_main(self):
        with patch.object(_mod, "get_repo_root", return_value="/tmp/repo"):
            assert main([]) == 2

    def test_prepare_body_file_does_not_require_title(self, tmp_path):
        with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
            assert main(["--prepare-body-file"]) == 0

    def test_valid_args(self):
        args = build_parser().parse_args(
            ["--title", "feat: test", "--base", "main"]
        )
        assert args.title == "feat: test"
        assert args.base == "main"

    def test_draft_flag(self):
        args = build_parser().parse_args(["--title", "fix: bug", "--draft"])
        assert args.draft is True

    def test_skip_validation_flag(self):
        args = build_parser().parse_args(
            [
                "--title",
                "fix: bug",
                "--skip-validation",
                "--audit-reason",
                "emergency",
            ]
        )
        assert args.skip_validation is True
        assert args.audit_reason == "emergency"


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


class TestMain:
    def test_gh_not_installed_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),
                _completed(rc=1),
            ],
        ):
            rc = main(["--title", "feat: test"])
        assert rc == 2

    def test_invalid_title_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),
                _completed(rc=0),
                _completed(stdout="feat/branch\n", rc=0),
            ],
        ):
            rc = main(["--title", "Bad title format"])
        assert rc == 2

    def test_skip_validation_without_reason_returns_2(self):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),
                _completed(rc=0),
                _completed(stdout="feat/branch\n", rc=0),
            ],
        ):
            rc = main(["--title", "feat: test", "--skip-validation"])
        assert rc == 2

    def test_successful_pr_creation(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(stdout="feat/branch\n", rc=0),
                _completed(stdout="", rc=0),
                _completed(stdout="{}", stderr="", rc=0),
                _completed(rc=0),
            ],
        ):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 0

    def test_body_file_not_found_returns_2(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(rc=0),
            ],
        ), patch.object(_mod, "run_validations"):
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/branch",
                    "--body-file",
                    "/nonexistent/file.md",
                ]
            )
        assert rc == 2

    def test_existing_body_file_outside_scratch_returns_2(self, tmp_path):
        body = tmp_path / "private-key.txt"
        body.write_text("secret", encoding="utf-8")
        with patch(
            "subprocess.run",
            side_effect=[_completed(stdout=str(tmp_path), rc=0)],
        ):
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/branch",
                    "--body-file",
                    str(body),
                ]
            )
        assert rc == 2

    def test_gh_pr_create_failure_returns_exit_code(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(rc=0),
                _completed(rc=1, stderr="error creating PR"),
            ],
        ), patch.object(_mod, "run_validations"):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 1

    def test_gh_pr_create_failure_keeps_stderr_when_output_redirected(
        self,
        tmp_path,
    ):
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
        subprocess.run(
            ["git", "init"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        body = _prepared_body(repo, "## Summary\n\nRegression test.\n")
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
                    body,
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
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(stdout="", rc=0),
            ],
        ):
            rc = main(["--title", "feat: test"])
        assert rc == 2

    def test_skip_validation_with_reason_writes_audit(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(rc=0),
            ],
        ), patch.object(_mod, "write_audit_log") as mock_audit:
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/branch",
                    "--skip-validation",
                    "--audit-reason",
                    "hotfix",
                ]
            )
        assert rc == 0
        mock_audit.assert_called_once()
        call_args = mock_audit.call_args
        assert call_args[0][4] == "hotfix"

    def test_validation_exception_returns_1(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(rc=0),
            ],
        ), patch(
            "new_pr.run_validations",
            side_effect=Exception("unexpected error"),
        ):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 1

    def test_body_file_used_when_provided(self, tmp_path):
        body_file = _prepared_body(tmp_path)
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),
                _completed(rc=0),
                _completed(rc=0),
                _completed(stdout="", rc=0),
                _completed(stdout="{}", stderr="", rc=0),
                _completed(rc=0),
            ],
        ):
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/branch",
                    "--body-file",
                    body_file,
                ]
            )
        assert rc == 0

    @pytest.mark.parametrize("body", ["PR body content", ""])
    def test_body_file_streams_utf8_to_gh_stdin(self, tmp_path, body):
        body_file = _prepared_body(tmp_path, body)
        create_call = None

        def _run(command, **kwargs):
            nonlocal create_call
            if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
                return _completed(stdout=str(tmp_path), rc=0)
            if command[:2] == ["gh", "--version"]:
                return _completed(rc=0)
            if command[:3] == ["gh", "pr", "create"]:
                create_call = (command, kwargs)
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=_run), patch(
            "new_pr.run_validations"
        ):
            assert (
                main(
                    [
                        "--title",
                        "feat: test",
                        "--head",
                        "feat/branch",
                        "--body-file",
                        body_file,
                    ]
                )
                == 0
            )

        assert create_call is not None
        command, kwargs = create_call
        assert command[-2:] == ["--body-file", "-"]
        assert kwargs["input"] == body
        assert kwargs["encoding"] == "utf-8"

    def test_draft_flag_passed(self, tmp_path):
        calls = []

        def _side_effect(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args", []))
            if len(calls) == 1:
                return _completed(stdout=str(tmp_path), rc=0)
            if len(calls) == 2:
                return _completed(rc=0)
            if len(calls) == 3:
                return _completed(stdout="", rc=0)
            if len(calls) == 4:
                return _completed(stdout="{}", stderr="", rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=_side_effect):
            rc = main(
                [
                    "--title",
                    "feat: test",
                    "--head",
                    "feat/branch",
                    "--draft",
                ]
            )
        assert rc == 0
        gh_pr_create_args = calls[-1]
        assert "--draft" in gh_pr_create_args


class TestMainUsesResolvedValidationBase:
    """main() uses a remote ref for validation and a bare GitHub base."""

    def _base_calls(self, branch: str = "feat/x"):
        return [
            _completed(rc=0),
            _completed(stdout=branch + "\n"),
            _completed(rc=0),
        ]

    def test_validation_base_uses_origin_ref_not_local(self, tmp_path):
        """run_validations receives origin/main when the ref resolves."""
        calls = self._base_calls()
        calls.append(_completed(rc=0))

        with patch("subprocess.run", side_effect=calls):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations") as mock_val:
                    main(["--title", "feat: test", "--base", "main"])

        mock_val.assert_called_once()
        assert mock_val.call_args[0][1] == "origin/main"

    def test_gh_pr_create_still_receives_bare_base(self, tmp_path):
        """gh pr create --base gets the bare branch, not origin/main."""
        captured: list[list[str]] = []

        def _side(argv, **kwargs):
            if argv and argv[0] == "gh" and "create" in argv:
                captured.append(list(argv))
                return _completed(rc=0)
            if argv and argv == ["git", "branch", "--show-current"]:
                return _completed(stdout="feat/x\n")
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=_side):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations"):
                    main(["--title", "feat: test", "--base", "main"])

        assert captured, "gh pr create never called"
        gh_argv = captured[-1]
        base_idx = gh_argv.index("--base")
        assert gh_argv[base_idx + 1] == "main"

    def test_explicit_validation_base_overrides_auto_resolve(self, tmp_path):
        """--validation-base bypasses origin resolution entirely."""
        calls = [
            _completed(rc=0),
            _completed(stdout="feat/x\n"),
            _completed(rc=0),
        ]

        with patch("subprocess.run", side_effect=calls):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations") as mock_val:
                    main(
                        [
                            "--title",
                            "feat: test",
                            "--base",
                            "main",
                            "--validation-base",
                            "refs/remotes/upstream/main",
                        ]
                    )

        mock_val.assert_called_once()
        assert mock_val.call_args[0][1] == "refs/remotes/upstream/main"

    def test_validation_base_falls_back_when_no_remote(self, tmp_path):
        """Without origin/<base>, validation uses the bare base."""
        calls = [
            _completed(rc=0),
            _completed(stdout="feat/x\n"),
            _completed(rc=1),
            _completed(rc=0),
        ]

        with patch("subprocess.run", side_effect=calls):
            with patch.object(_mod, "get_repo_root", return_value=str(tmp_path)):
                with patch.object(_mod, "run_validations") as mock_val:
                    main(["--title", "feat: test", "--base", "main"])

        mock_val.assert_called_once()
        assert mock_val.call_args[0][1] == "main"

    def test_build_parser_accepts_validation_base(self):
        args = build_parser().parse_args(
            [
                "--title",
                "feat: test",
                "--base",
                "main",
                "--validation-base",
                "origin/main",
            ]
        )
        assert args.validation_base == "origin/main"

    def test_build_parser_validation_base_defaults_to_empty(self):
        args = build_parser().parse_args(["--title", "feat: test"])
        assert args.validation_base == ""
