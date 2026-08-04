# taste-lint: ignore file-size, test coverage for four separate push-gate issues
"""Tests for push-gate reliability fixes.

Covers:
- #4472: budget-exhaustion timeout message
- #4492: push_files contamination guard
- #4511: portability write-lock files are gitignored
- #4502: pytest.yml test job has timeout-minutes
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[bytes]:
    cp: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess(
        args=[], returncode=returncode
    )
    cp.stdout = stdout.encode()
    cp.stderr = stderr.encode()
    return cp


# ---------------------------------------------------------------------------
# #4472: budget-exhaustion message
# ---------------------------------------------------------------------------


class TestBudgetExhaustionMessage:
    """run_pytest emits a budget-exhaustion message when a command times out
    after the budget was partially consumed by earlier commands."""

    def _run_pytest_with_timeout(
        self,
        remaining: float,
        full_budget: float,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> tuple[int, str]:
        """Call run_pytest with one command that times out at `remaining`."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS",
            full_budget,
        )

        deadline_value = [0.0]

        def fake_monotonic() -> float:
            return deadline_value[0]

        # First call: set deadline; subsequent calls: advance clock so
        # `remaining` = full_budget - (time elapsed)
        call_count = [0]

        def monotonic_side_effect() -> float:
            call_count[0] += 1
            if call_count[0] == 1:
                # Initial call that sets deadline
                deadline_value[0] = 0.0
                return 0.0
            # After first command runs: simulate that (full_budget - remaining) elapsed
            return full_budget - remaining

        monkeypatch.setattr("time.monotonic", monotonic_side_effect)

        timeout_result = _make_completed(3)
        timeout_result.stdout = b""
        timeout_result.stderr = b""

        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._run_command",
            lambda *a, **kw: timeout_result,
        )
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._pytest_commands",
            lambda root: [["uv", "run", "python", "-m", "pytest"]],
        )
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._print_process_output",
            lambda r: None,
        )
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._clean_git_env",
            lambda: {},
        )

        import io

        captured = io.StringIO()
        monkeypatch.setattr("sys.stderr", captured)

        rc = policy.run_pytest(tmp_path)
        return rc, captured.getvalue()

    def test_budget_exhausted_emits_exhaustion_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Timeout with remaining < full budget -> budget-exhaustion message."""
        full_budget = 1740.0
        remaining = 200.0  # earlier commands consumed most of the budget

        rc, stderr = self._run_pytest_with_timeout(remaining, full_budget, monkeypatch, tmp_path)

        assert rc == 3
        assert "budget exhausted" in stderr.lower() or "budget" in stderr

    def test_full_budget_timeout_no_exhaustion_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Timeout when full budget remains -> plain timeout, no budget-exhaustion claim."""
        full_budget = 1740.0
        remaining = full_budget  # first command, budget untouched

        rc, stderr = self._run_pytest_with_timeout(remaining, full_budget, monkeypatch, tmp_path)

        assert rc == 3
        # No budget-exhaustion message when remaining == full_budget
        assert "budget exhausted" not in stderr.lower()

    def test_zero_remaining_exits_before_running(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """remaining <= 0 triggers early exit with rc=1 before running any command."""
        full_budget = 1740.0

        monkeypatch.setattr(
            "scripts.validation.git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS",
            full_budget,
        )

        call_count = [0]

        def monotonic_side_effect() -> float:
            call_count[0] += 1
            # First call sets deadline; second call returns deadline (remaining=0)
            return 0.0 if call_count[0] == 1 else full_budget

        monkeypatch.setattr("time.monotonic", monotonic_side_effect)
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._pytest_commands",
            lambda root: [["uv", "run", "python", "-m", "pytest"]],
        )
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._clean_git_env",
            lambda: {},
        )

        run_called = [False]

        def fake_run(*a: object, **kw: object) -> subprocess.CompletedProcess[bytes]:
            run_called[0] = True
            return _make_completed(0)

        monkeypatch.setattr("scripts.validation.git_hook_policy._run_command", fake_run)

        import io

        captured = io.StringIO()
        monkeypatch.setattr("sys.stderr", captured)

        rc = policy.run_pytest(tmp_path)
        assert rc == 1
        assert not run_called[0]


# ---------------------------------------------------------------------------
# #4492: push_files contamination guard
# ---------------------------------------------------------------------------


class TestPushFilesGuard:
    """_push_files_are_genuine filters contaminated {push_files} sets."""

    def test_genuine_file_returns_true(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A push_file that appears in origin/main...HEAD -> genuine."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._branch_delta_files",
            lambda root, base="origin/main": {"scripts/validation/portability_common.py"},
        )
        assert policy._push_files_are_genuine(
            ["scripts/validation/portability_common.py"], tmp_path
        )

    def test_contaminated_file_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A push_file absent from origin/main...HEAD -> contaminated."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._branch_delta_files",
            lambda root, base="origin/main": {"scripts/validation/portability_common.py"},
        )
        assert not policy._push_files_are_genuine(
            [".claude/skills/some-skill/SKILL.md"], tmp_path
        )

    def test_empty_push_files_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Empty push_files list -> False (nothing to run the gate on)."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._branch_delta_files",
            lambda root, base="origin/main": {"any/file.py"},
        )
        assert not policy._push_files_are_genuine([], tmp_path)

    def test_unresolvable_base_returns_true(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When origin/main is unresolvable, fall back to True (run unconditionally)."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._branch_delta_files",
            lambda root, base="origin/main": None,
        )
        assert policy._push_files_are_genuine([".claude/skills/x/SKILL.md"], tmp_path)

    def test_run_cli_e2e_skips_on_contaminated_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """run_cli_e2e exits 0 without running pytest when files are contaminated."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._push_files_are_genuine",
            lambda files, root: False,
        )
        run_called = [False]

        def fake_run(*a: object, **kw: object) -> subprocess.CompletedProcess[bytes]:
            run_called[0] = True
            return _make_completed(0)

        monkeypatch.setattr("scripts.validation.git_hook_policy._run_command", fake_run)

        rc = policy.run_cli_e2e("tests/e2e/test_plugin_load_smoke.py", tmp_path, ["some/file.md"])
        assert rc == 0
        assert not run_called[0]

    def test_run_cli_e2e_proceeds_on_genuine_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """run_cli_e2e proceeds past the guard when files are genuine."""
        monkeypatch.setattr(
            "scripts.validation.git_hook_policy._push_files_are_genuine",
            lambda files, root: True,
        )
        monkeypatch.setattr("shutil.which", lambda x: None)

        rc = policy.run_cli_e2e("tests/e2e/test_plugin_load_smoke.py", tmp_path, ["real/file.py"])
        # No CLI installed -> skip with rc=0 (existing behavior)
        assert rc == 0

    def test_run_cli_e2e_no_push_files_arg_runs_normally(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """run_cli_e2e with push_files=None bypasses the guard entirely."""
        monkeypatch.setattr("shutil.which", lambda x: None)
        rc = policy.run_cli_e2e("tests/e2e/test_plugin_load_smoke.py", tmp_path, None)
        assert rc == 0

    def test_cli_plugin_e2e_subcommand_accepts_files_arg(self) -> None:
        """The cli-plugin-e2e subcommand accepts --files."""
        parser = policy.build_parser()
        args = parser.parse_args(["cli-plugin-e2e", "--files", "a/b.md", "c/d.py"])
        assert args.files == ["a/b.md", "c/d.py"]

    def test_cli_hook_e2e_subcommand_accepts_files_arg(self) -> None:
        """The cli-hook-e2e subcommand accepts --files."""
        parser = policy.build_parser()
        args = parser.parse_args(["cli-hook-e2e", "--files", "x/y.md"])
        assert args.files == ["x/y.md"]


# ---------------------------------------------------------------------------
# #4511: portability write-lock files are gitignored
# ---------------------------------------------------------------------------


class TestPortabilityWriteLockIgnored:
    """The two advisory write-lock files are gitignored."""

    def _check_ignored(self, path: str, repo_root: Path) -> bool:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=repo_root,
            capture_output=True,
        )
        return result.returncode == 0

    def test_skill_md_portability_lock_is_ignored(self, tmp_path: Path) -> None:
        """scripts/validation/.skill_md_portability_baseline.json.write-lock is ignored."""
        # Use the real repo root (this test must run from inside the worktree)
        repo_root = Path(__file__).parent.parent.parent
        lock_path = "scripts/validation/.skill_md_portability_baseline.json.write-lock"
        assert self._check_ignored(lock_path, repo_root), (
            f"{lock_path} is not gitignored; add it to .gitignore under the portability section"
        )

    def test_skill_md_exec_portability_lock_is_ignored(self, tmp_path: Path) -> None:
        """scripts/validation/.skill_md_exec_portability_baseline.json.write-lock is ignored."""
        repo_root = Path(__file__).parent.parent.parent
        lock_path = "scripts/validation/.skill_md_exec_portability_baseline.json.write-lock"
        assert self._check_ignored(lock_path, repo_root), (
            f"{lock_path} is not gitignored; add it to .gitignore under the portability section"
        )

    def test_normal_json_file_in_scripts_validation_not_ignored(self) -> None:
        """A normal baseline JSON file should not be gitignored."""
        repo_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            ["git", "check-ignore", "-q", "scripts/validation/skill_md_portability_baseline.json"],
            cwd=repo_root,
            capture_output=True,
        )
        # rc=1 means NOT ignored (expected); rc=0 means ignored (unexpected)
        assert result.returncode == 1, (
            "scripts/validation/skill_md_portability_baseline.json should not be gitignored"
        )

    def test_lock_file_elsewhere_not_ignored_by_anchored_rule(self) -> None:
        """Gitignore rule is anchored; same filename outside scripts/validation is not ignored."""
        repo_root = Path(__file__).parent.parent.parent
        # A lock file in a different directory should not be matched by an anchored rule
        result = subprocess.run(
            ["git", "check-ignore", "-q", "tests/.skill_md_portability_baseline.json.write-lock"],
            cwd=repo_root,
            capture_output=True,
        )
        # Expected: NOT ignored (rc=1). An unanchored rule would incorrectly ignore this.
        assert result.returncode == 1, (
            "The write-lock gitignore rule must be anchored to scripts/validation/; "
            "tests/.skill_md_portability_baseline.json.write-lock should NOT be ignored"
        )


# ---------------------------------------------------------------------------
# #4502: pytest.yml test job has timeout-minutes
# ---------------------------------------------------------------------------


class TestPytestYmlTimeout:
    """The test job in .github/workflows/pytest.yml has a timeout-minutes key."""

    def test_test_job_has_timeout_minutes(self) -> None:
        """The 'test' job in pytest.yml must have timeout-minutes set."""
        import yaml

        repo_root = Path(__file__).parent.parent.parent
        workflow_path = repo_root / ".github/workflows/pytest.yml"
        assert workflow_path.exists(), f"{workflow_path} not found"

        with open(workflow_path, encoding="utf-8") as fh:
            workflow = yaml.safe_load(fh)

        test_job = workflow.get("jobs", {}).get("test", {})
        assert "timeout-minutes" in test_job, (
            "The 'test' job in pytest.yml is missing timeout-minutes; "
            "a hung suite will burn the 360-minute GitHub default"
        )

    def test_test_job_timeout_minutes_is_reasonable(self) -> None:
        """timeout-minutes for the test job should be between 20 and 90 minutes."""
        import yaml

        repo_root = Path(__file__).parent.parent.parent
        workflow_path = repo_root / ".github/workflows/pytest.yml"
        with open(workflow_path, encoding="utf-8") as fh:
            workflow = yaml.safe_load(fh)

        timeout = workflow.get("jobs", {}).get("test", {}).get("timeout-minutes")
        assert timeout is not None
        assert 20 <= timeout <= 90, (
            f"test job timeout-minutes={timeout} is outside the expected range [20, 90]"
        )
