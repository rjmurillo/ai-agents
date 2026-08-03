"""Tests for new_pr.py skill script."""

from __future__ import annotations

import ast
import codecs
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


def _fake_git(
    repo_root: str = "/repo",
    *,
    diff: str = "",
    pr_create_rc: int = 0,
    pr_create_stderr: str = "",
    remotes: str = "origin\n",
):
    """Dispatch a fake subprocess on argv instead of on call order.

    Positional ``side_effect`` lists broke every time ``main`` gained a
    subprocess call, and their comments drifted out of alignment with the real
    sequence: passing ``--head`` skips the ``git branch`` lookup entirely, so
    the entry labelled ``git branch`` was being consumed by the next call.
    """

    def _run(cmd, *_args, **_kwargs):
        argv = list(cmd)
        if argv[0] == sys.executable:
            return _completed(stdout="{}", rc=0)
        if argv[:3] == ["gh", "pr", "create"]:
            return _completed(stdout="https://pr", stderr=pr_create_stderr, rc=pr_create_rc)
        if argv[0] == "gh":
            return _completed(rc=0)
        if argv[:2] == ["git", "rev-parse"]:
            if "--show-toplevel" in argv:
                return _completed(stdout=repo_root, rc=0)
            return _completed(rc=0)
        if argv[:2] == ["git", "remote"]:
            return _completed(stdout=remotes, rc=0)
        if argv[:2] == ["git", "branch"]:
            return _completed(stdout="feat/branch\n", rc=0)
        if argv[:2] == ["git", "diff"]:
            return _completed(stdout=diff, rc=0)
        raise AssertionError(f"unstubbed subprocess call: {argv}")

    return _run



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
        with patch("subprocess.run", side_effect=_fake_git(str(tmp_path))):
            rc = main(["--title", "feat: test", "--head", "feat/branch"])
        assert rc == 0

    def test_body_file_not_found_returns_2(self, tmp_path):
        with patch("subprocess.run", side_effect=_fake_git(str(tmp_path))):
            rc = main([
                "--title", "feat: test", "--head", "feat/branch",
                "--body-file", "/nonexistent/file.md",
            ])
        assert rc == 2

    def test_gh_pr_create_failure_returns_exit_code(self, tmp_path):
        with patch(
            "subprocess.run",
            side_effect=_fake_git(
                str(tmp_path), pr_create_rc=1, pr_create_stderr="error creating PR"
            ),
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
                _completed(rc=0),  # git rev-parse origin/main (comparison base)
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


class TestRunValidations:
    def test_no_agents_changes_skips(self, tmp_path):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")

    def test_skill_violation_scan_skipped_when_git_diff_fails(self, tmp_path, capsys):
        """A failed git diff must NOT run detect_skill_violation.py with zero
        --file args (which would trigger a full-repo scan and 30s timeout), and
        must NOT silently masquerade as 'no changes'. Instead it warns visibly
        and skips the change-scoped scan (Copilot review, issue #3006)."""
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(rc=128, stderr="fatal: bad revision")
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        # detect_skill_violation.py must never be invoked on a failed diff.
        assert not any(
            len(cmd) >= 2 and cmd[1] == str(skill_script) for cmd in calls
        )
        captured = capsys.readouterr()
        assert "git diff" in captured.err and "failed" in captured.err
        # Validation 1 (Session End) must also honor the failed diff: it must
        # report the skip explicitly, not masquerade as "No .agents/ changes".
        assert "Skipped: git diff failed" in captured.out
        assert "No .agents/ changes, skipping" not in captured.out

    def test_skill_violation_detection_scopes_to_changed_files(self, tmp_path):
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        changed = "scripts/changed.py\ndocs/guide.md\n"
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        skill_calls = [c for c in calls if len(c) >= 2 and c[1] == str(skill_script)]
        assert skill_calls == [
            [
                sys.executable,
                str(skill_script),
                "--file",
                "scripts/changed.py",
                "--file",
                "docs/guide.md",
            ]
        ]

    def test_skill_violation_scan_skipped_when_no_scannable_extension(
        self, tmp_path, capsys
    ):
        """When every changed file has an unscannable extension, the scanner
        subprocess must be skipped entirely (issue #3010) and the skip reported."""
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        changed = "assets/logo.png\ndata/table.json\nMakefile\n"
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        assert not any(len(cmd) >= 2 and cmd[1] == str(skill_script) for cmd in calls)
        captured = capsys.readouterr()
        assert "No changed files with a scannable extension" in captured.out

    def test_skill_violation_scan_filters_unscannable_extensions(self, tmp_path):
        """A mixed changed-file list must pass only scannable extensions to the
        scanner argv, dropping the rest (issue #3010)."""
        skill_script = tmp_path / "scripts" / "detect_skill_violation.py"
        skill_script.parent.mkdir(parents=True)
        skill_script.write_text("# mock")
        changed = "scripts/mod.py\nassets/logo.png\ndocs/guide.md\nhooks/setup.ps1\ndata/x.json\n"
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        skill_calls = [c for c in calls if len(c) >= 2 and c[1] == str(skill_script)]
        assert skill_calls == [
            [
                sys.executable,
                str(skill_script),
                "--file",
                "scripts/mod.py",
                "--file",
                "docs/guide.md",
                "--file",
                "hooks/setup.ps1",
            ]
        ]

    def test_skill_scan_extensions_match_detector(self):
        """The local _SKILL_SCAN_EXTENSIONS constant must stay in sync with the
        scanner's VALID_EXTENSIONS (drift guard, issue #3010). It is a local copy
        by design: the two synced new_pr.py trees sit at different repo depths, so
        cross-package importing scripts/detect_skill_violation.py is avoided (same
        rationale documented for _DASH_RE)."""
        detector_path = (
            Path(__file__).resolve().parents[1] / "scripts" / "detect_skill_violation.py"
        )
        mod_key = "detect_skill_violation_drift_guard"
        spec = importlib.util.spec_from_file_location(mod_key, detector_path)
        assert spec is not None and spec.loader is not None
        detector = importlib.util.module_from_spec(spec)
        # detect_skill_violation.py uses @dataclass, whose decorator resolves
        # cls.__module__ via sys.modules, so the module must be registered
        # before exec_module. Register under a unique key and restore prior
        # state in finally to avoid leaking global sys.modules state into other
        # tests (gemini-code-assist review, PR #3012).
        previous = sys.modules.get(mod_key)
        sys.modules[mod_key] = detector
        # detect_skill_violation.py mutates global sys.path at import time
        # (sys.path.insert(0, project_root)); snapshot and restore it in finally
        # so the insertion cannot leak into later tests and create
        # order-dependent failures (copilot review, PR #3012).
        sys_path_snapshot = list(sys.path)
        try:
            spec.loader.exec_module(detector)
            assert _mod._SKILL_SCAN_EXTENSIONS == detector.VALID_EXTENSIONS
        finally:
            if previous is not None:
                sys.modules[mod_key] = previous
            else:
                sys.modules.pop(mod_key, None)
            sys.path[:] = sys_path_snapshot

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
        # The validated path is ignored repo-local scratch, not the branch log path.
        assert Path(validated_paths[0]).parent == (
            tmp_path / ".agents" / "scratch" / "session-log-validation"
        )
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


class TestACrashedValidatorIsNotSuccess:
    """A validator that never ran must not read as a clean scan.

    detect_test_coverage_gaps.py died on an import error while this wrapper
    printed "All pre-creation validations passed", so a broken quality gate
    produced success-shaped output and the PR was created anyway (#3391).
    Both warning-only detectors document exit 0 as "ran, findings are
    warnings", so any non-zero code is the validator failing, not a finding.
    """

    @staticmethod
    def _run(tmp_path, *, coverage_rc: int, skill_rc: int = 0, title: str = "feat: x"):
        for name in ("detect_test_coverage_gaps.py", "detect_skill_violation.py"):
            script = tmp_path / "scripts" / name
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text("# mock", encoding="utf-8")

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout="src/main.py\n", rc=0)
            if len(cmd) > 1 and cmd[1].endswith("detect_test_coverage_gaps.py"):
                return _completed(stderr="ModuleNotFoundError\n", rc=coverage_rc)
            if len(cmd) > 1 and cmd[1].endswith("detect_skill_violation.py"):
                return _completed(rc=skill_rc)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch", title=title)

    def test_a_crashed_coverage_detector_blocks_creation(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            self._run(tmp_path, coverage_rc=1)
        assert exc.value.code == 1
        assert "All pre-creation validations passed" not in capsys.readouterr().out

    def test_the_message_names_the_validator_that_did_not_run(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._run(tmp_path, coverage_rc=1)
        stderr = capsys.readouterr().err
        assert "detect_test_coverage_gaps.py" in stderr
        assert "did not run" in stderr

    def test_a_crashed_skill_detector_blocks_too(self, tmp_path, capsys):
        """The same swallow existed on validation 2."""
        with pytest.raises(SystemExit):
            self._run(tmp_path, coverage_rc=0, skill_rc=2)
        assert "detect_skill_violation.py" in capsys.readouterr().err

    def test_the_detector_output_still_reaches_the_operator(self, tmp_path, capsys):
        """Capturing the subprocess must not hide what it printed."""
        with pytest.raises(SystemExit):
            self._run(tmp_path, coverage_rc=1)
        assert "ModuleNotFoundError" in capsys.readouterr().err

    def test_clean_detectors_still_report_success(self, tmp_path, capsys):
        """Negative control: the block must be keyed on the failure."""
        self._run(tmp_path, coverage_rc=0)
        assert "All pre-creation validations passed" in capsys.readouterr().out


class TestCapturedOutputPinsItsCodec:
    """Every capturing subprocess.run must pin utf-8, on both mirrors.

    subprocess.run(text=True) with no encoding decodes with
    locale.getpreferredencoding(False). On Windows that is cp1252, and the
    reader thread raises UnicodeDecodeError on the UTF-8 bytes git and gh
    routinely emit (branch names, commit subjects, gh's status glyphs). The
    exception surfaces in a helper thread rather than the caller, so
    subprocess.run returns with stdout set to None instead of raising. Callers
    that then do result.stdout.strip() die with AttributeError; callers that
    check truthiness silently treat a crashed tool as one that printed nothing.

    That last shape is the exact failure issue #3391 exists to prevent, so this
    file must not reintroduce it. An AST check rather than a grep so a new call
    site is covered the day it is written.

    Scoped to calls that both capture and decode. A run() with no capture
    inherits the parent's stdio and never decodes, so text= is inert there and
    the codec is not its concern.
    """

    _MIRRORS = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py",
        Path(__file__).resolve().parents[1]
        / "src" / "copilot-cli" / "skills" / "github" / "scripts" / "pr" / "new_pr.py",
    )

    @staticmethod
    def _set_true(kwargs: dict[str, ast.expr], name: str) -> bool:
        """True when the keyword is present and spelled as a truthy literal."""
        value = kwargs.get(name)
        return isinstance(value, ast.Constant) and bool(value.value)

    @staticmethod
    def _pins_utf8(encoding: ast.expr | None) -> bool:
        """True when encoding= resolves to the canonical UTF-8 codec."""
        if not isinstance(encoding, ast.Constant) or not isinstance(encoding.value, str):
            return False
        try:
            return codecs.lookup(encoding.value).name == "utf-8"
        except LookupError:
            return False

    @staticmethod
    def _capturing_runs(source: str):
        """(lineno, {kwarg names}) for each subprocess.run that decodes output."""
        found = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "run"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            set_true = TestCapturedOutputPinsItsCodec._set_true
            captures = (
                set_true(kwargs, "capture_output")
                or "stdout" in kwargs
                or "stderr" in kwargs
            )
            decodes = (
                set_true(kwargs, "text")
                or set_true(kwargs, "universal_newlines")
                or "encoding" in kwargs
                or "errors" in kwargs
            )
            if captures and decodes:
                present = set(kwargs)
                if not TestCapturedOutputPinsItsCodec._pins_utf8(kwargs.get("encoding")):
                    present.discard("encoding")
                found.append((node.lineno, present))
        return found

    @pytest.mark.parametrize("mirror", _MIRRORS, ids=lambda p: p.parts[-6])
    def test_every_capturing_run_pins_utf8(self, mirror):
        offenders = [
            lineno
            for lineno, kwargs in self._capturing_runs(mirror.read_text(encoding="utf-8"))
            if "encoding" not in kwargs
        ]
        assert not offenders, (
            f"{mirror}: subprocess.run at line(s) {offenders} captures and decodes "
            "output without encoding='utf-8'; this crashes the reader thread on "
            "Windows cp1252 and returns stdout=None"
        )

    @pytest.mark.parametrize("mirror", _MIRRORS, ids=lambda p: p.parts[-6])
    def test_every_capturing_run_survives_undecodable_bytes(self, mirror):
        """errors= must be set too: a pinned codec still raises without it."""
        offenders = [
            lineno
            for lineno, kwargs in self._capturing_runs(mirror.read_text(encoding="utf-8"))
            if "errors" not in kwargs
        ]
        assert not offenders, (
            f"{mirror}: subprocess.run at line(s) {offenders} pins a codec but no "
            "errors= policy, so undecodable bytes raise instead of degrading"
        )

    def test_the_check_finds_something_to_check(self):
        """Vacuity control: an AST walk that matches nothing proves nothing."""
        runs = self._capturing_runs(self._MIRRORS[0].read_text(encoding="utf-8"))
        assert len(runs) >= 5

    def test_a_bare_text_run_is_reported(self):
        """Negative control on the walker itself."""
        offenders = self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=True)\n"
        )
        assert offenders == [(2, {"capture_output", "text"})]

    def test_errors_alone_run_is_reported(self):
        """errors= alone enables text mode through the locale codec."""
        offenders = self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], capture_output=True, errors='ignore')\n"
        )
        assert offenders == [(2, {"capture_output", "errors"})]

    def test_errors_with_encoding_is_not_an_encoding_offender(self):
        """errors= with encoding= pins the codec and stays quiet."""
        runs = self._capturing_runs(
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, encoding='utf-8', errors='ignore')\n"
        )
        offenders = [lineno for lineno, kwargs in runs if "encoding" not in kwargs]
        assert offenders == []

    def test_utf8_codec_aliases_are_not_encoding_offenders(self):
        """Python codec aliases that resolve to UTF-8 still pin the codec."""
        source = "\n".join(
            [
                "import subprocess",
                *(
                    "subprocess.run(['x'], capture_output=True, "
                    f"encoding={alias!r}, errors='replace')"
                    for alias in ("UTF-8", "utf8", "UTF8", "utf_8", "U8")
                ),
            ]
        )
        runs = self._capturing_runs(source)

        offenders = [lineno for lineno, kwargs in runs if "encoding" not in kwargs]

        assert len(runs) == 5
        assert offenders == []

    @pytest.mark.parametrize("codec", ("latin-1", "utf-8-sig", "not-a-codec"))
    def test_non_utf8_codecs_are_encoding_offenders(self, codec):
        """Non-UTF-8 codecs still fail the pinned-codec guard."""
        runs = self._capturing_runs(
            "import subprocess\n"
            f"subprocess.run(['x'], capture_output=True, encoding={codec!r}, errors='replace')\n"
        )
        offenders = [lineno for lineno, kwargs in runs if "encoding" not in kwargs]

        assert offenders == [2]

    def test_a_non_capturing_run_is_out_of_scope(self):
        """text= without capture never decodes, so it is not this rule's business."""
        assert self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], text=True, check=False)\n"
        ) == []


# ---------------------------------------------------------------------------
# Tests: Validation 6 (escaped-newline check on body, Issue #3777)
# ---------------------------------------------------------------------------


class TestValidation6EscapedNewlineCheck:
    """Validation 6 rejects an inline body whose line breaks are literal.

    Issue #3777. Two issues (#3598, #3646) shipped with every line break
    written as the two characters backslash and n, so GitHub rendered each as
    one unbroken paragraph and dropped every heading, list and table.

    new_pr.py carries a second copy of the predicate rather than importing
    scripts/github_core/validation.py::escaped_newline_body_error, because
    new_pr.py resolves only its own directory on sys.path and a lib bootstrap
    would hard-exit 2 whenever .claude/lib is absent on the push path. These
    tests pin the copy; tests/test_github_core.py pins the canonical version.
    """

    @staticmethod
    def _validate(tmp_path, *, body, body_file=None):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(
                str(tmp_path), "main", "feat/branch",
                title="feat: clean title",
                body=body,
                body_file=body_file,
            )

    def test_escaped_newlines_with_no_real_break_blocks(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="## Summary\\n\\nDetail\\n- item")
        assert excinfo.value.code == 1

    def test_error_names_the_count_and_the_remedy(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._validate(tmp_path, body="a\\nb\\nc")
        err = capsys.readouterr().err
        assert "2 literal backslash-n" in err
        assert "--body-file" in err

    def test_trailing_newline_only_body_still_blocks(self, tmp_path):
        """The measured shape of #3598: 15 escapes plus 1 real newline."""
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="## Summary\\n\\nDetail\\n" + "\n")
        assert excinfo.value.code == 1

    def test_escaped_newline_inside_a_real_multiline_body_passes(
        self, tmp_path, capsys
    ):
        self._validate(
            tmp_path, body='## Notes\n\n```python\nprint("a\\nb")\n```\n'
        )
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_normal_body_passes(self, tmp_path, capsys):
        self._validate(tmp_path, body="## Summary\n\nDetail\n")
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_single_line_body_without_escapes_passes(self, tmp_path, capsys):
        self._validate(tmp_path, body="Just one line.")
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_body_file_contents_are_checked_too(self, tmp_path):
        """--body-file is the recommended remedy, so it must not be a bypass."""
        path = tmp_path / "body.md"
        path.write_text("## Summary\\n\\nDetail", encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="", body_file=str(path))
        assert excinfo.value.code == 1

    def test_quoted_canonical_predicate_is_verbatim(self):
        """The docstring calls its quote verbatim, so check it against source.

        The first version of this quote was a fragment: it omitted the
        ``if not body`` guard, so "verbatim" was false. The docstring was
        also a non-raw string, which turned the quoted ``"\\n"`` into a real
        newline at runtime, so even the fragment was not reproduced. Both
        defects are invisible to a reader who trusts the word "verbatim",
        which is why this compares the two texts instead.
        """
        import ast
        import textwrap

        repo_root = Path(__file__).resolve().parent.parent
        canonical = repo_root / "scripts" / "github_core" / "validation.py"
        tree = ast.parse(canonical.read_text(encoding="utf-8"))
        func = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "escaped_newline_body_error"
        )
        # Skip the docstring statement; the quote covers the code that follows.
        body_start = func.body[1].lineno
        lines = canonical.read_text(encoding="utf-8").splitlines()

        for mirror in (
            ".claude/skills/github/scripts/pr/validate_pr_description.py",
            "src/copilot-cli/skills/github/scripts/pr/validate_pr_description.py",
        ):
            mod = ast.parse((repo_root / mirror).read_text(encoding="utf-8"))
            copy = next(
                n
                for n in ast.walk(mod)
                if isinstance(n, ast.FunctionDef)
                and n.name == "validate_no_escaped_newlines"
            )
            doc = ast.get_docstring(copy, clean=False)
            assert doc is not None, mirror
            marker = "body::"
            assert marker in doc, f"{mirror}: citation marker missing"
            quoted = textwrap.dedent(
                doc.split(marker, 1)[1].split("\n\n", 2)[1]
            ).strip("\n")
            quoted_lines = quoted.splitlines()
            # Without this, an empty quote would compare [] to [] and pass.
            assert len(quoted_lines) >= 5, (
                f"{mirror}: quote too short to be the guard plus predicate: "
                f"{quoted_lines!r}"
            )
            actual = [
                line[4:] for line in lines[body_start - 1 : body_start - 1 + len(quoted_lines)]
            ]
            assert quoted_lines == actual, (
                f"{mirror}: quote is not verbatim.\n"
                f"quoted={quoted_lines!r}\nactual={actual!r}"
            )

    def test_chain_is_renumbered_to_six_steps(self, tmp_path, capsys):
        self._validate(tmp_path, body="## Summary\n\nDetail\n")
        out = capsys.readouterr().out
        for step in range(1, 7):
            assert f"[{step}/6]" in out, f"missing step {step}/6"


# ---------------------------------------------------------------------------
# Tests: resolve_comparison_base
# ---------------------------------------------------------------------------


def _remote_then(probe_rc: int, remotes: str = "origin\n"):
    """side_effect for the resolver's two calls: git remote, then rev-parse."""
    return [_completed(stdout=remotes, rc=0), _completed(rc=probe_rc)]


class TestResolveComparisonBase:
    """The diff base must prefer the remote-tracking ref.

    A local ``main`` goes stale while you work on feature branches. Diffing
    against it inflates the changed-file set with everything merged upstream
    since, which makes Session End validation pick a stranger's session log.
    """

    def test_prefers_remote_tracking_ref_when_it_exists(self):
        with patch("subprocess.run", side_effect=_remote_then(0)):
            assert _mod.resolve_comparison_base("main") == "refs/remotes/origin/main"

    def test_probes_a_fully_qualified_ref_not_the_dwim_shorthand(self):
        # A local branch literally named origin/main outranks refs/remotes in
        # git's rev search order, so the shorthand would silently resolve to the
        # wrong commit and reintroduce the stale-base bug.
        with patch("subprocess.run", side_effect=_remote_then(0)) as run:
            _mod.resolve_comparison_base("main")
        probed = run.call_args_list[-1][0][0]
        assert "refs/remotes/origin/main^{commit}" in probed
        assert "origin/main^{commit}" not in probed

    def test_falls_back_when_remote_ref_is_missing(self):
        with patch("subprocess.run", side_effect=_remote_then(128)):
            assert _mod.resolve_comparison_base("local-only") == "local-only"

    def test_base_already_remote_qualified_is_left_alone(self):
        # refs/remotes/origin/origin/main never exists, so the probe fails.
        with patch("subprocess.run", side_effect=_remote_then(128)):
            assert _mod.resolve_comparison_base("origin/main") == "origin/main"

    def test_slashed_branch_name_still_resolves(self):
        with patch("subprocess.run", side_effect=_remote_then(0)):
            assert (
                _mod.resolve_comparison_base("release/1.0")
                == "refs/remotes/origin/release/1.0"
            )

    def test_single_non_origin_remote_is_used(self):
        with patch("subprocess.run", side_effect=_remote_then(0, "upstream\n")):
            assert (
                _mod.resolve_comparison_base("main") == "refs/remotes/upstream/main"
            )

    def test_several_remotes_without_origin_falls_back(self):
        # No non-arbitrary choice exists, so do not guess.
        with patch(
            "subprocess.run", side_effect=[_completed(stdout="fork\nupstream\n", rc=0)]
        ):
            assert _mod.resolve_comparison_base("main") == "main"

    def test_no_remotes_at_all_falls_back(self):
        with patch("subprocess.run", side_effect=[_completed(stdout="", rc=0)]):
            assert _mod.resolve_comparison_base("main") == "main"

    def test_git_remote_failure_falls_back(self):
        with patch("subprocess.run", side_effect=[_completed(rc=128)]):
            assert _mod.resolve_comparison_base("main") == "main"

    def test_both_calls_strip_git_hook_env_overrides(self, monkeypatch):
        monkeypatch.setenv("GIT_DIR", "/wrong/git")
        with patch("subprocess.run", side_effect=_remote_then(0)) as run:
            _mod.resolve_comparison_base("main")
        for call in run.call_args_list:
            assert "GIT_DIR" not in call.kwargs["env"]


class TestComparisonBaseIsNotThePullRequestTarget:
    """Validation diffs against the remote ref; the PR still targets the base.

    Resolving the PR target too would ask gh to open a pull request against a
    branch named ``refs/remotes/origin/main``, which does not exist on the
    server.
    """

    def test_validation_uses_remote_ref_but_pr_targets_plain_base(self):
        seen: dict = {}

        def _fake_validations(repo_root, base, head, **kwargs):
            seen["validation_base"] = base

        with patch.object(_mod, "run_validations", _fake_validations), patch(
            "subprocess.run",
            side_effect=[
                _completed(stdout="/tmp/repo", rc=0),      # git rev-parse --show-toplevel
                _completed(rc=0),                           # gh --version
                _completed(stdout="origin\n", rc=0),        # git remote
                _completed(rc=0),                           # git rev-parse refs/remotes/...
                _completed(stdout="https://pr", rc=0),      # gh pr create
            ],
        ) as run:
            main(["--title", "feat: test", "--head", "feat/x", "--body", "b"])

        assert seen["validation_base"] == "refs/remotes/origin/main"
        gh_args = run.call_args_list[-1][0][0]
        assert gh_args[:3] == ["gh", "pr", "create"]
        assert gh_args[gh_args.index("--base") + 1] == "main"


class TestSessionEndFailureIsDiagnosable:
    """The abort must say which log it chose and why, and show the validator.

    The bare one-line form was byte-identical to the failure you get from
    amending after recording endingCommit, so readers hunted for an amend they
    never made.
    """

    def _fail_on(self, tmp_path, changed: str):
        repo = tmp_path
        (repo / "scripts").mkdir(parents=True, exist_ok=True)
        (repo / "scripts" / "validate_session_json.py").write_text("")

        def _side_effect(cmd, *a, **kw):
            if cmd[:2] == ["git", "diff"]:
                return _completed(stdout=changed, rc=0)
            if cmd and cmd[0] == sys.executable:
                return _completed(
                    stdout="[FAIL] endingCommit is not an ancestor\n",
                    stderr="detail on stderr\n",
                    rc=1,
                )
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=_side_effect), patch.object(
            _mod, "_session_log_for_validation"
        ) as ctx:
            ctx.return_value.__enter__ = lambda s: str(
                repo / "scripts" / "validate_session_json.py"
            )
            ctx.return_value.__exit__ = lambda s, *a: False
            with pytest.raises(SystemExit):
                run_validations(str(repo), "main", "feat/x", title="feat: t", body="b")

    def test_names_the_selected_log_and_prints_validator_output(self, tmp_path, capsys):
        self._fail_on(
            tmp_path,
            ".agents/sessions/2026-01-01-session-9-mine.json\n"
            ".agents/sessions/2026-01-02-session-10-someone-else.json\n",
        )
        err = capsys.readouterr().err
        # The newest by (date, session number) is the one it validated.
        assert "2026-01-02-session-10-someone-else.json" in err
        assert "newest" in err
        assert "fetch" in err
        assert "endingCommit is not an ancestor" in err  # validator stdout
        assert "detail on stderr" in err                  # validator stderr

    def test_sorts_numerically_not_lexically(self, tmp_path, capsys):
        self._fail_on(
            tmp_path,
            ".agents/sessions/2026-01-01-session-9-nine.json\n"
            ".agents/sessions/2026-01-01-session-10-ten.json\n",
        )
        err = capsys.readouterr().err
        assert "session-10-ten.json" in err
        assert "session-9-nine.json" not in err
