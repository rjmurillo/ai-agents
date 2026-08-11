"""Pre-creation validation pipeline tests for new_pr.py.

Split from the former single ``tests/test_new_pr.py`` (issue #4764), which had
grown to 1,390 lines and mixed unrelated responsibilities in one module. The
shared import of the script under test and the subprocess helpers live in
``tests/new_pr_harness.py`` so no module re-derives them.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

from tests.new_pr_harness import (
    _UNTRUSTED_REPOSITORY_VALIDATORS,
    SCRIPTS_DIR,
    run_validations,
    write_audit_log,
)
from tests.new_pr_harness import (
    completed as _completed,
)
from tests.new_pr_harness import (
    new_pr as _mod,
)

_SCRIPTS_DIR = SCRIPTS_DIR


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

    def test_skill_violation_detection_skips_changed_scripts(
        self, tmp_path, capsys
    ):
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
        assert skill_calls == []
        assert "outside the trusted push-pr boundary" in capsys.readouterr().out

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
        assert "Not run: skill violation (scripts/detect_skill_violation.py)." in captured.out

    def test_skill_violation_scan_skips_mixed_scripts_change(
        self, tmp_path, capsys
    ):
        """A scripts/ change makes the repository-local scanner untrusted."""
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
        assert skill_calls == []
        assert "outside the trusted push-pr boundary" in capsys.readouterr().out

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

    def test_agents_changed_session_validator_is_not_executed(
        self, tmp_path, capsys
    ):
        changed = ".agents/sessions/2025-01-01-session-01.json\n"
        validate_script = tmp_path / "scripts" / "validate_session_json.py"
        validate_script.parent.mkdir(parents=True)
        validate_script.write_text("# mock")

        with patch(
            "subprocess.run",
            return_value=_completed(stdout=changed, rc=0),
        ):
            run_validations(str(tmp_path), "main", "feat/branch")
        assert (
            "Not run: Session End (scripts/validate_session_json.py)."
            in capsys.readouterr().out
        )

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

        assert validated_paths == []

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
        assert (
            "Not run: Session End (scripts/validate_session_json.py)."
            in capsys.readouterr().out
        )

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


class TestRepositoryValidatorTrust:
    """The three repository-local detectors are never run from /push-pr.

    Issue #4764 put repository-controlled Python outside the trust boundary.
    Issue #4825 review 4894113215 finding 1 reported that the previous code
    reached that outcome through a helper that ignored its arguments, always
    returned False, printed "scripts/ is changed or dirty" on a clean branch,
    and still summarized the run as "All pre-creation validations passed!".
    These tests pin the replacement contract: the same three checks are named
    as not run on every branch state, and the summary says so.
    """

    _EXPECTED = (
        "Session End (scripts/validate_session_json.py)",
        "skill violation (scripts/detect_skill_violation.py)",
        "test coverage (scripts/detect_test_coverage_gaps.py)",
    )

    def test_untrusted_validator_inventory_is_explicit(self):
        assert _UNTRUSTED_REPOSITORY_VALIDATORS == self._EXPECTED

    def _run(self, tmp_path, changed, capsys, rc=0):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout=changed, rc=rc)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")
        return capsys.readouterr().out

    # A session log makes Validation 1 applicable, so all three slots report.
    _SESSION_LOG = ".agents/sessions/2026-08-10-session-1-guard.json\n"

    def test_clean_branch_reports_every_check_as_not_run(self, tmp_path, capsys):
        """Positive case: no scripts/ change, nothing dirty, still not run."""
        out = self._run(tmp_path, self._SESSION_LOG + "docs/guide.md\n", capsys)

        for validator in self._EXPECTED:
            assert f"Not run: {validator}." in out
        assert "outside the trusted push-pr boundary" in out
        assert "All pre-creation validations passed" not in out
        assert "scripts/ is changed or dirty" not in out

    def test_changed_scripts_branch_reports_the_same_outcome(self, tmp_path, capsys):
        """Negative case: a scripts/ change does not change the outcome."""
        out = self._run(
            tmp_path,
            self._SESSION_LOG + "scripts/detect_test_coverage_gaps.py\n",
            capsys,
        )

        for validator in self._EXPECTED:
            assert f"Not run: {validator}." in out

    def test_summary_names_the_checks_that_did_not_run(self, tmp_path, capsys):
        out = self._run(tmp_path, "docs/guide.md\n", capsys)

        assert "Trusted pre-creation validations passed." in out
        assert "3 repository-local check(s) did not run" in out
        for validator in self._EXPECTED:
            assert validator in out

    def test_no_repository_validator_subprocess_is_spawned(self, tmp_path):
        """Edge case: the trust boundary is enforced by not executing, not by
        executing and ignoring the result."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(
                    stdout=".agents/sessions/2026-08-10-session-1-x.json\ndocs/a.md\n",
                    rc=0,
                )
            return _completed(rc=0)

        (tmp_path / "scripts").mkdir()
        for name in (
            "validate_session_json.py",
            "detect_skill_violation.py",
            "detect_test_coverage_gaps.py",
        ):
            (tmp_path / "scripts" / name).write_text("# mock", encoding="utf-8")

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(str(tmp_path), "main", "feat/branch")

        spawned = [
            cmd
            for cmd in calls
            if any("scripts/" in str(part) and str(part).endswith(".py") for part in cmd)
        ]
        assert spawned == []


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestRepositoryValidatorsNeverExecute:
    def test_repository_python_is_outside_push_pr_tcb(self, tmp_path, capsys):
        scripts = []
        for name in ("detect_test_coverage_gaps.py", "detect_skill_violation.py"):
            script = tmp_path / "scripts" / name
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(
                "raise RuntimeError('must not execute')\n",
                encoding="utf-8",
            )
            scripts.append(str(script))

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:3] == ["git", "diff", "--name-only"]:
                return _completed(stdout="src/main.py\n", rc=0)
            return _completed(rc=0)

        with patch("subprocess.run", side_effect=fake_run):
            run_validations(
                str(tmp_path),
                "main",
                "feat/branch",
                title="feat: x",
            )

        assert not any(
            len(cmd) > 1 and str(cmd[1]) in scripts
            for cmd in calls
        )
        output = capsys.readouterr().out
        assert "Not run: skill violation (scripts/detect_skill_violation.py)." in output
        assert "Not run: test coverage (scripts/detect_test_coverage_gaps.py)." in output
        assert "Trusted pre-creation validations passed" in output
        assert "All pre-creation validations passed" not in output


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
