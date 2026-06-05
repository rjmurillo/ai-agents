"""Tests for new_pr.py skill script."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import the script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / ".claude" / "skills" / "github" / "scripts" / "pr"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("new_pr")
main = _mod.main
build_parser = _mod.build_parser
validate_conventional_commit = _mod.validate_conventional_commit
get_repo_root = _mod.get_repo_root
run_validations = _mod.run_validations
write_audit_log = _mod.write_audit_log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


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
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(stdout="feat/branch\n", rc=0),  # git branch
                _completed(stdout="", rc=0),  # git diff
            ],
        ):
            rc = main([
                "--title", "feat: test", "--head", "feat/branch",
                "--body-file", "/nonexistent/file.md",
            ])
        assert rc == 2

    def test_gh_pr_create_failure_returns_exit_code(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
                _completed(rc=1, stderr="error creating PR"),  # gh pr create
            ],
        ), patch("new_pr.run_validations"):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 1

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
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
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
                _completed(stdout=str(tmp_path), rc=0),  # git rev-parse
                _completed(rc=0),  # gh --version
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


class TestRunValidations:
    def test_no_agents_changes_skips(self, tmp_path):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")

    def test_agents_changed_with_session_log_runs_validator(self, tmp_path):
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")

        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=changed, rc=0),  # git diff
                _completed(stdout='{"ok": true}\n', rc=0),  # git show <head>:<path>
                _completed(rc=0),  # python validation
            ],
        ):
            run_validations(str(tmp_path), "main", "feat/branch")

    def test_agents_changed_session_validation_fails_exits_1(self, tmp_path):
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")

        with patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout=changed, rc=0),  # git diff
                _completed(stdout='{"ok": false}\n', rc=0),  # git show <head>:<path>
                _completed(rc=1, stderr="validation failed"),  # python validation
            ],
        ):
            with pytest.raises(SystemExit) as exc:
                run_validations(str(tmp_path), "main", "feat/branch")
            assert exc.value.code == 1

    def test_session_log_read_from_branch_ref_not_working_tree(self, tmp_path):
        """Session log is validated from head:<path>, not the working tree (#2387).

        The branch is not checked out, so repo_root/<path> is absent. The
        validator must still run against content read from the ref via
        git show, not fail with an opaque error.
        """
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        # Note: no .agents/sessions file is written into tmp_path, so the
        # working-tree path does not exist; only git show can supply content.

        validated_paths: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(stdout='{"session": 1}\n', rc=0)
            if cmd[0].endswith("python") or "validate_session_json.py" in " ".join(cmd):
                validated_paths.append(cmd[-1])
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/not-checked-out")

        assert len(validated_paths) == 1
        # The validated path is scratch under .agents, not the branch worktree path.
        assert Path(validated_paths[0]).parent == tmp_path / ".agents"
        assert not Path(validated_paths[0]).name.endswith("session-01.json")

    def test_session_log_missing_from_head_skips_validation(self, tmp_path, capsys):
        """When the head ref lacks the log, do not validate a stale worktree copy."""
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")
        stale = tmp_path / ".agents" / "sessions" / "2025-01-01-session-01.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text('{"stale": true}\n', encoding="utf-8")

        validator_ran = False

        def fake_run(cmd, **kwargs):
            nonlocal validator_ran
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            if cmd[:2] == ["git", "show"]:
                return _completed(rc=128, stderr="path does not exist")
            if "validate_session_json.py" in " ".join(cmd):
                validator_ran = True
                return _completed(rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert validator_ran is False
        assert "not found at feat/branch" in capsys.readouterr().err

    def test_agents_changed_no_session_log_warns(self, tmp_path, capsys):
        changed = ".agents/HANDOFF.md\n"
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=changed, rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        stderr = capsys.readouterr().err
        assert "WARNING" in stderr

    def test_agents_changed_legacy_md_session_log_only_warns_once(
        self, tmp_path, capsys
    ):
        """When only legacy .md session logs are staged, the helper warns
        about migration; the calling code MUST NOT also print
        'No session log found' (devin-ai-integration finding on PR #1980).
        """
        changed = ".agents/sessions/2026-05-10-session-1830.md\n"
        with patch(
            "subprocess.run",
            return_value=_completed(stdout=changed, rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        stderr = capsys.readouterr().err
        assert "legacy .md session log" in stderr
        assert "No session log found" not in stderr

    def test_permission_error_on_mkdir_warns(self, tmp_path, capsys):
        with patch("os.makedirs", side_effect=PermissionError("denied")), patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        stderr = capsys.readouterr().err
        assert "Could not create .agents directory" in stderr


# ---------------------------------------------------------------------------
# Tests: write_audit_log
# ---------------------------------------------------------------------------


class TestWriteAuditLog:
    def test_creates_audit_file(self, tmp_path):
        write_audit_log(str(tmp_path), "feat/branch", "main", "feat: test", "hotfix")
        audit_dir = tmp_path / ".agents" / "audit"
        assert audit_dir.exists()
        files = list(audit_dir.glob("pr-creation-skip-*.txt"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "feat/branch" in content
        assert "hotfix" in content
        assert "SKIPPED" in content

    def test_uses_username_env(self, tmp_path):
        with patch.dict(os.environ, {"USERNAME": "testuser"}, clear=False):
            write_audit_log(str(tmp_path), "feat/b", "main", "feat: t", "reason")
        files = list((tmp_path / ".agents" / "audit").glob("*.txt"))
        content = files[0].read_text()
        assert "testuser" in content

    def test_falls_back_to_user_env(self, tmp_path):
        env = {k: v for k, v in os.environ.items() if k not in ("USERNAME",)}
        env["USER"] = "fallbackuser"
        with patch.dict(os.environ, env, clear=True):
            write_audit_log(str(tmp_path), "feat/b", "main", "feat: t", "reason")
        files = list((tmp_path / ".agents" / "audit").glob("*.txt"))
        content = files[0].read_text()
        assert "fallbackuser" in content


# ---------------------------------------------------------------------------
# Tests: Validation 5 (em/en-dash check on title and body, Issue #1923)
# ---------------------------------------------------------------------------


class TestValidation5DashCheck:
    """Tests for Validation 5: em/en-dash guard on PR title and body."""

    def test_clean_title_and_body_passes(self, tmp_path, capsys):
        """No dashes in either title or body, run_validations completes."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(
                str(tmp_path), "main", "feat/branch",
                title="feat: clean title",
                body="body without dashes",
            )
        out = capsys.readouterr()
        assert "No prohibited characters" in out.out

    def test_em_dash_in_title_blocks(self, tmp_path):
        """Em-dash in title raises SystemExit(1)."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title=f"feat: bad {chr(0x2014)} title",
                    body="clean body",
                )
            except SystemExit as e:
                assert e.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_en_dash_in_body_blocks(self, tmp_path):
        """En-dash in body raises SystemExit(1)."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title="feat: clean",
                    body=f"range {chr(0x2013)} 10",
                )
            except SystemExit as e:
                assert e.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_dash_in_body_file_blocks(self, tmp_path):
        """Em-dash in body-file path raises SystemExit(1)."""
        body_file = tmp_path / "body.md"
        body_file.write_text(
            f"# Body\n\nLine with em-dash {chr(0x2014)} here\n",
            encoding="utf-8",
        )
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title="feat: clean",
                    body_file=str(body_file),
                )
            except SystemExit as e:
                assert e.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_em_dash_error_message_includes_line_number(self, tmp_path, capsys):
        """Error stderr includes specific line numbers for actionable output."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title="feat: clean",
                    body=f"line 1 clean\nline 2 has {chr(0x2014)} dash\nline 3 clean\n",
                )
            except SystemExit:
                pass
            stderr = capsys.readouterr().err
            assert "line 2" in stderr
            # After refactor (commit 467353d0) to use validate_no_dashes from
            # scripts.validation.pr_description, the error wording is
            # "PR description contains U+2014 or U+2013 (line N). ..."
            assert "U+2014" in stderr or "U+2013" in stderr
