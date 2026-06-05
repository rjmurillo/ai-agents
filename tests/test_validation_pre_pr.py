"""Tests for scripts.validation.pre_pr module.

Validates the pre-PR validation runner including individual validations,
result tracking, and CLI behavior. External tool calls are mocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.validation.pre_pr import (
    ValidationState,
    _find_latest_session_log,
    _parse_yaml_frontmatter,
    _run_subprocess,
    build_parser,
    main,
    run_validation,
    validate_command_bundle_coverage,
    validate_design_review_frontmatter,
    validate_review_marker,
    validate_session_end,
    validate_workflow_yaml,
)

# ---------------------------------------------------------------------------
# _find_latest_session_log
# ---------------------------------------------------------------------------


class TestFindLatestSessionLog:
    """Tests for session log discovery."""

    def test_returns_none_when_no_directory(self, tmp_path: Path) -> None:
        assert _find_latest_session_log(tmp_path) is None

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        assert _find_latest_session_log(tmp_path) is None

    def test_finds_latest_log(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("old", encoding="utf-8")
        (sessions / "2025-12-02-session-1.md").write_text("new", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-02-session-1.md"

    def test_ignores_non_matching_files(self, tmp_path: Path) -> None:
        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "README.md").write_text("not a log", encoding="utf-8")
        (sessions / "2025-12-01-session-1.md").write_text("log", encoding="utf-8")

        result = _find_latest_session_log(tmp_path)
        assert result is not None
        assert result.name == "2025-12-01-session-1.md"


# ---------------------------------------------------------------------------
# _run_subprocess
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    """Tests for subprocess runner."""

    def test_successful_command(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["echo", "hello"])
        assert exit_code == 0
        assert "hello" in stdout

    def test_command_not_found(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(
            ["nonexistent_command_xyz_123"]
        )
        assert exit_code == -1
        assert "not found" in stderr.lower() or "Command not found" in stderr


# ---------------------------------------------------------------------------
# ValidationState / run_validation
# ---------------------------------------------------------------------------


class TestRunValidation:
    """Tests for validation runner and state tracking."""

    def test_passing_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: True)
        assert result is True
        assert state.total == 1
        assert state.passed == 1
        assert state.failed == 0

    def test_failing_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: False)
        assert result is False
        assert state.total == 1
        assert state.passed == 0
        assert state.failed == 1

    def test_skipped_validation(self) -> None:
        state = ValidationState()
        result = run_validation("Test Check", state, lambda: True, skip=True)
        assert result is True
        assert state.total == 1
        assert state.skipped == 1
        assert state.passed == 0

    def test_exception_counts_as_failure(self) -> None:
        def raise_error() -> bool:
            raise RuntimeError("boom")

        state = ValidationState()
        result = run_validation("Test Check", state, raise_error)
        assert result is False
        assert state.failed == 1

    def test_missing_script_skip_does_not_fail(self) -> None:
        """MissingScriptSkip should be reported as SKIP, not FAIL.

        Regression guard for issue #1850: pre_pr.py must not produce FAIL
        lines for PowerShell scripts expunged per ADR-042.
        """
        from scripts.validation.pre_pr import MissingScriptSkip

        def raise_skip() -> bool:
            raise MissingScriptSkip("Some-Validator.ps1 not present")

        state = ValidationState()
        result = run_validation("Test Check", state, raise_skip)
        assert result is True  # SKIP must not block the gate
        assert state.skipped == 1
        assert state.failed == 0
        assert state.passed == 0
        assert state.results[0].status == "SKIP"

    def test_records_duration(self) -> None:
        state = ValidationState()
        run_validation("Test Check", state, lambda: True)
        assert state.results[0].duration >= 0

    def test_multiple_validations(self) -> None:
        state = ValidationState()
        run_validation("Check 1", state, lambda: True)
        run_validation("Check 2", state, lambda: False)
        run_validation("Check 3", state, lambda: True, skip=True)

        assert state.total == 3
        assert state.passed == 1
        assert state.failed == 1
        assert state.skipped == 1
        assert len(state.results) == 3


# ---------------------------------------------------------------------------
# validate_session_end
# ---------------------------------------------------------------------------


class TestValidateSessionEnd:
    """Tests for session end validation."""

    def test_no_session_log_returns_true(self, tmp_path: Path) -> None:
        result = validate_session_end(tmp_path)
        assert result is True

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import MissingScriptSkip

        sessions = tmp_path / ".agents" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "2025-12-01-session-1.md").write_text("log", encoding="utf-8")
        # scripts/Validate-Session.ps1 does not exist (ADR-042 expungement).
        (tmp_path / "scripts").mkdir(exist_ok=True)

        import pytest

        with pytest.raises(MissingScriptSkip):
            validate_session_end(tmp_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _parse_yaml_frontmatter
# ---------------------------------------------------------------------------


class TestParseYamlFrontmatter:
    """Tests for YAML frontmatter parser."""

    def test_parses_valid_frontmatter(self) -> None:
        text = '---\nstatus: "APPROVED"\npriority: "P1"\nblocking: false\n---\n# Title\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"
        assert result["blocking"] is False

    def test_returns_none_without_frontmatter(self) -> None:
        text = "# Title\nSome content\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_returns_none_for_unclosed_frontmatter(self) -> None:
        text = "---\nstatus: APPROVED\n# No closing delimiter\n"
        assert _parse_yaml_frontmatter(text) is None

    def test_parses_boolean_true(self) -> None:
        text = "---\nblocking: true\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["blocking"] is True

    def test_parses_integer_values(self) -> None:
        text = "---\npr: 1205\nissue: 937\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["pr"] == 1205
        assert result["issue"] == 937

    def test_strips_quotes(self) -> None:
        text = '---\nstatus: "BLOCKED"\nreviewer: \'architect\'\n---\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "BLOCKED"
        assert result["reviewer"] == "architect"

    def test_skips_comments_and_blank_lines(self) -> None:
        text = "---\n# comment\n\nstatus: APPROVED\n---\n"
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert len(result) == 1

    def test_strips_inline_yaml_comments(self) -> None:
        text = (
            "---\n"
            "status: APPROVED              # APPROVED | NEEDS_CHANGES\n"
            "priority: P1  # severity\n"
            "---\n"
        )
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["status"] == "APPROVED"
        assert result["priority"] == "P1"

    def test_preserves_hash_inside_quotes(self) -> None:
        text = '---\nvalue: "has # in it"\n---\n'
        result = _parse_yaml_frontmatter(text)
        assert result is not None
        assert result["value"] == "has # in it"


# ---------------------------------------------------------------------------
# validate_design_review_frontmatter
# ---------------------------------------------------------------------------


class TestValidateDesignReviewFrontmatter:
    """Tests for DESIGN-REVIEW frontmatter validation."""

    def _write_review(self, tmp_path: Path, name: str, content: str) -> Path:
        """Helper to create a DESIGN-REVIEW file."""
        review_dir = tmp_path / ".agents" / "architecture"
        review_dir.mkdir(parents=True, exist_ok=True)
        filepath = review_dir / name
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_no_directory_returns_true(self, tmp_path: Path) -> None:
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_no_review_files_returns_true(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "architecture").mkdir(parents=True)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_valid_frontmatter_passes(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_missing_frontmatter_fails(self, tmp_path: Path) -> None:
        content = "# Design Review: Test\nNo frontmatter here.\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_missing_required_fields_fails(self, tmp_path: Path) -> None:
        content = '---\nstatus: "APPROVED"\n---\n# Design Review: Test\n'
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_status_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "INVALID"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_invalid_priority_fails(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "APPROVED"\npriority: "P99"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        assert validate_design_review_frontmatter(tmp_path) is False

    def test_blocking_review_detected(self, tmp_path: Path) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: true\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)
        # Blocking reviews still pass validation (they just warn)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_blocking_null_does_not_count_as_blocking(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        content = (
            '---\nstatus: "BLOCKED"\npriority: "P0"\n'
            'blocking: null\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review: Test\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-test.md", content)

        assert validate_design_review_frontmatter(tmp_path) is True

        captured = capsys.readouterr()
        assert "should have blocking: true" in captured.out
        assert "blocking review(s) detected" not in captured.out

    def test_multiple_files_all_valid(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", valid)
        assert validate_design_review_frontmatter(tmp_path) is True

    def test_one_invalid_among_valid_fails(self, tmp_path: Path) -> None:
        valid = (
            '---\nstatus: "APPROVED"\npriority: "P1"\n'
            'blocking: false\nreviewer: "architect"\ndate: "2026-03-07"\n'
            "---\n# Design Review\n"
        )
        invalid = "# No frontmatter\n"
        self._write_review(tmp_path, "DESIGN-REVIEW-a.md", valid)
        self._write_review(tmp_path, "DESIGN-REVIEW-b.md", invalid)
        assert validate_design_review_frontmatter(tmp_path) is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.quick is False
        assert args.skip_tests is False
        assert args.verbose is False

    def test_quick_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--quick"])
        assert args.quick is True

    def test_skip_tests_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--skip-tests"])
        assert args.skip_tests is True

    def test_verbose_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True


class TestMain:
    """Integration tests for main entry point.

    External tool calls are mocked to avoid requiring actual tools.
    """

    @patch("scripts.validation.pre_pr._run_subprocess")
    def test_quick_mode_skips_slow_checks(self, mock_subprocess: Any) -> None:  # noqa: ANN401
        mock_subprocess.return_value = (0, "", "")

        # Quick mode should skip path normalization, planning, agent drift, yaml style
        result = main(["--quick", "--skip-tests"])
        # Should not fail since all checks pass or are skipped
        assert result in (0, 1)  # May fail if scripts don't exist

    @patch("scripts.validation.pre_pr._run_subprocess")
    @patch("scripts.validation.pre_pr.shutil")
    def test_all_pass_returns_zero(
        self, mock_shutil: Any, mock_subprocess: Any  # noqa: ANN401
    ) -> None:
        mock_subprocess.return_value = (0, "", "")
        mock_shutil.which.return_value = "/usr/bin/npx"

        # All external tools pass
        result = main(["--quick", "--skip-tests"])
        assert result in (0, 1)


# ---------------------------------------------------------------------------
# validate_command_bundle_coverage  (SPEC-005 AC-14)
# ---------------------------------------------------------------------------


class TestValidateCommandBundleCoverage:
    """Tests for the SPEC-005 bundle coverage advisory check.

    Behavior contract:

    - All present: returns ``True``.
    - Any missing, ``BUNDLE_CHECK_ENFORCED`` unset / 0: returns ``True``
      (advisory WARN, never blocks pre-PR).
    - Any missing, ``BUNDLE_CHECK_ENFORCED=1``: returns ``False``
      (escalates to BLOCKING).
    - bundle_registry import failure with enforcement off: returns
      ``True`` (advisory skip; import failure must not block pre_pr).
    - bundle_registry import failure with enforcement on: returns
      ``False``.
    """

    def setup_method(self) -> None:
        """Drop any cached ``bundle_registry`` so each test sees the
        fake from its own tmp_path (or no module, in failure tests)."""
        import sys

        sys.modules.pop("bundle_registry", None)

    teardown_method = setup_method

    def _make_repo(
        self,
        tmp_path: Path,
        registry: list[tuple[str, str]],
        present: set[tuple[str, str]],
    ) -> Path:
        """Build a fake repo root with a vendored bundle_registry and
        ``.claude/commands/`` files for the given ``present`` pairs."""
        # Lay out a vendored bundle_registry.py the validator can import.
        validation_dir = tmp_path / "scripts" / "validation"
        validation_dir.mkdir(parents=True)
        registry_literal = ",\n    ".join(
            f"({cmd!r}, {skill!r})" for cmd, skill in registry
        )
        (validation_dir / "bundle_registry.py").write_text(
            "BUNDLE_REGISTRY = [\n    "
            + registry_literal
            + "\n]\n"
            "def expected_skill_invocation(skill):\n"
            "    return f'Skill(skill=\"{skill}\")'\n",
            encoding="utf-8",
        )

        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        # Only write the command files that are 'present' in the registry.
        # Group invocations by command file.
        bodies: dict[str, list[str]] = {}
        for cmd, skill in present:
            bodies.setdefault(cmd, []).append(f'Skill(skill="{skill}")')
        for cmd, lines in bodies.items():
            (commands_dir / cmd).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return tmp_path

    def test_all_present_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        registry = [("spec.md", "session-init"), ("ship.md", "session-end")]
        repo = self._make_repo(tmp_path, registry, present=set(registry))
        monkeypatch.delenv("BUNDLE_CHECK_ENFORCED", raising=False)
        assert validate_command_bundle_coverage(repo) is True

    def test_missing_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        registry = [("spec.md", "session-init"), ("ship.md", "session-end")]
        repo = self._make_repo(
            tmp_path,
            registry,
            present={("spec.md", "session-init")},  # ship.md missing
        )
        monkeypatch.delenv("BUNDLE_CHECK_ENFORCED", raising=False)
        # Advisory: missing must NOT fail the gate.
        assert validate_command_bundle_coverage(repo) is True

    def test_missing_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        registry = [("spec.md", "session-init"), ("ship.md", "session-end")]
        repo = self._make_repo(
            tmp_path,
            registry,
            present={("spec.md", "session-init")},  # ship.md missing
        )
        monkeypatch.setenv("BUNDLE_CHECK_ENFORCED", "1")
        assert validate_command_bundle_coverage(repo) is False

    def test_empty_registry_passes(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, registry=[], present=set())
        monkeypatch.delenv("BUNDLE_CHECK_ENFORCED", raising=False)
        assert validate_command_bundle_coverage(repo) is True

    def test_import_failure_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Import failure path: pre-poison ``sys.modules`` with a stub
        that raises ``ImportError`` on attribute access, simulating a
        broken or absent bundle_registry. Advisory mode must NOT block
        pre_pr."""
        import sys

        class BrokenModule:
            def __getattr__(self, name: str) -> Any:  # noqa: ANN401
                raise ImportError(f"simulated import failure for {name}")

        monkeypatch.setitem(sys.modules, "bundle_registry", BrokenModule())
        monkeypatch.delenv("BUNDLE_CHECK_ENFORCED", raising=False)
        assert validate_command_bundle_coverage(tmp_path) is True

    def test_import_failure_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        """Same as the advisory case but with enforcement on. Must
        return ``False`` so pre_pr surfaces the failure."""
        import sys

        class BrokenModule:
            def __getattr__(self, name: str) -> Any:  # noqa: ANN401
                raise ImportError(f"simulated import failure for {name}")

        monkeypatch.setitem(sys.modules, "bundle_registry", BrokenModule())
        monkeypatch.setenv("BUNDLE_CHECK_ENFORCED", "1")
        assert validate_command_bundle_coverage(tmp_path) is False


# ---------------------------------------------------------------------------
# validate_dash_prohibition (Issue #1923, REQ-006-AC7, M4)
# ---------------------------------------------------------------------------


class TestValidateDashProhibition:
    """Tests for the branch-wide em/en-dash check."""

    def test_returns_true_when_no_base_ref_resolves(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        # tmp_path is not a git repo; no ref will resolve.
        assert validate_dash_prohibition(tmp_path) is True

    def test_returns_true_for_clean_branch(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "README.md\n", ""),  # git diff
                (0, "clean content\n", ""),  # git show
            ]
            assert validate_dash_prohibition(tmp_path) is True

    def test_returns_false_on_em_dash(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        # _find_dash_violations now reads HEAD content via `git show`
        # rather than the working tree. Mock the two subprocess calls
        # in order: (1) git diff returns the file list, (2) git show
        # returns the file content as if from HEAD.
        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "doc.md\n", ""),  # git diff
                (0, f"prose with {chr(0x2014)} em-dash\n", ""),  # git show
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_returns_false_on_en_dash(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "range.md\n", ""),
                (0, f"range 1{chr(0x2013)}10\n", ""),
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_skips_vendored_paths(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        vendored = tmp_path / "node_modules" / "pkg" / "README.md"
        vendored.parent.mkdir(parents=True)
        vendored.write_text(f"upstream prose with {chr(0x2014)} dash\n", encoding="utf-8")
        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "node_modules/pkg/README.md\n", "")
            assert validate_dash_prohibition(tmp_path) is True

    def test_skips_test_fixtures_dir(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_dash_prohibition

        fixture = tmp_path / "tests" / "hooks" / "fixtures" / "dash_violations.md"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(f"intentional {chr(0x2014)}\n", encoding="utf-8")
        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (0, "tests/hooks/fixtures/dash_violations.md\n", "")
            assert validate_dash_prohibition(tmp_path) is True

    def test_includes_github_instructions_tree(self, tmp_path: Path) -> None:
        """REQ-006-AC4: .github/instructions/ is NOT excluded."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, ".github/instructions/universal.instructions.md\n", ""),
                (0, f"prose {chr(0x2014)} dash\n", ""),
            ]
            assert validate_dash_prohibition(tmp_path) is False

    def test_returns_true_when_git_diff_fails(self, tmp_path: Path) -> None:
        """Fail open on git subprocess failure (do not block on infra issues)."""
        from scripts.validation.pre_pr import validate_dash_prohibition

        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.return_value = (128, "", "fatal: bad revision")
            assert validate_dash_prohibition(tmp_path) is True

    def test_reads_head_content_not_working_tree(self, tmp_path: Path) -> None:
        """`_find_dash_violations` reads HEAD via `git show`, not the working tree.

        Working-tree edit could differ from committed content. The branch-wide
        scan must reflect what is committed (HEAD), since the diff scope
        comes from `git diff base...HEAD`.
        """
        from scripts.validation.pre_pr import validate_dash_prohibition

        # Working tree clean, but HEAD content (mocked) has em-dash:
        # the function MUST flag it.
        with patch("scripts.validation.pre_pr._resolve_branch_base_ref") as mock_ref, \
             patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_ref.return_value = "origin/main"
            mock_run.side_effect = [
                (0, "doc.md\n", ""),
                # HEAD content has dash; working tree (clean) does not.
                (0, f"committed em-dash {chr(0x2014)} here\n", ""),
            ]
            # No file at tmp_path/doc.md (working tree). Function should
            # still detect the violation because it reads HEAD content.
            assert validate_dash_prohibition(tmp_path) is False


# ---------------------------------------------------------------------------
# validate_git_hooks_installed
# ---------------------------------------------------------------------------


class TestValidateGitHooksInstalled:
    """The local-githooks gate delegates to install_git_hooks.py --check."""

    def test_skipped_under_github_actions(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import (
            MissingScriptSkip,
            validate_git_hooks_installed,
        )

        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False):
            with pytest.raises(MissingScriptSkip):
                validate_git_hooks_installed(tmp_path)

    def test_skipped_under_ci(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import (
            MissingScriptSkip,
            validate_git_hooks_installed,
        )

        env = {"CI": "1"}
        with patch.dict("os.environ", env, clear=False):
            # Ensure GITHUB_ACTIONS does not mask the CI branch.
            import os

            os.environ.pop("GITHUB_ACTIONS", None)
            with pytest.raises(MissingScriptSkip):
                validate_git_hooks_installed(tmp_path)

    def test_not_skipped_when_ci_is_false(self, tmp_path: Path) -> None:
        """CI=false should not skip the check."""
        import os

        from scripts.validation.pre_pr import validate_git_hooks_installed

        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "install_git_hooks.py").write_text("# stub\n")
        env = {"CI": "false"}
        with patch.dict("os.environ", env, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                mock_run.return_value = (0, "OK", "")
                assert validate_git_hooks_installed(tmp_path) is True

    def test_missing_script_fails_closed(self, tmp_path: Path) -> None:
        import os

        from scripts.validation.pre_pr import validate_git_hooks_installed

        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            os.environ.pop("CI", None)
            assert validate_git_hooks_installed(tmp_path) is False

    def test_passes_when_check_exits_zero(self, tmp_path: Path) -> None:
        import os

        from scripts.validation.pre_pr import validate_git_hooks_installed

        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "install_git_hooks.py").write_text("# stub\n")
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            os.environ.pop("CI", None)
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                mock_run.return_value = (0, "OK", "")
                assert validate_git_hooks_installed(tmp_path) is True

    def test_fails_when_check_exits_nonzero(self, tmp_path: Path) -> None:
        import os

        from scripts.validation.pre_pr import validate_git_hooks_installed

        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "install_git_hooks.py").write_text("# stub\n")
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            os.environ.pop("CI", None)
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                mock_run.return_value = (1, "", "core.hooksPath not set")
                assert validate_git_hooks_installed(tmp_path) is False

    def test_delegates_to_hook_installer_outside_ci(self, tmp_path: Path) -> None:
        """Outside CI the gate delegates to the hook installer check."""
        import os

        from scripts.validation.pre_pr import validate_git_hooks_installed

        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "install_git_hooks.py").write_text("# stub\n")
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_ACTIONS", None)
            os.environ.pop("CI", None)
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                mock_run.return_value = (0, "OK", "")
                assert validate_git_hooks_installed(tmp_path) is True

            mock_run.assert_called_once()
            command = mock_run.call_args.args[0]
            repo_root_index = command.index("--repo-root")
            assert "--check" in command
            assert command[repo_root_index + 1] == str(tmp_path)


# ---------------------------------------------------------------------------
# validate_workflow_yaml (actionlint scoping, issue #2346)
# ---------------------------------------------------------------------------


class TestValidateWorkflowYamlScope:
    """actionlint validates workflows only; composite action.yml files under
    .github/actions/ must never be passed to it (issue #2346)."""

    @staticmethod
    def _build_tree(root: Path) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text(
            "on: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n",
            encoding="utf-8",
        )
        actions = root / ".github" / "actions" / "composite"
        actions.mkdir(parents=True)
        # A composite action: actionlint would emit false errors if scanned.
        (actions / "action.yml").write_text(
            "name: composite\nruns:\n  using: composite\n  steps: []\n",
            encoding="utf-8",
        )

    def test_does_not_pass_composite_action_paths(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("scripts.validation.pre_pr.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                assert validate_workflow_yaml(tmp_path) is True

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        assert command[0] == "actionlint"
        paths = command[1:]
        # No composite action path is ever handed to actionlint.
        assert all(".github/actions" not in p for p in paths)
        assert not any(p.endswith("action.yml") for p in paths)

    def test_passes_only_workflow_files(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("scripts.validation.pre_pr.shutil.which", return_value="/usr/bin/actionlint"):
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                mock_run.return_value = (0, "", "")
                validate_workflow_yaml(tmp_path)

        command = mock_run.call_args.args[0]
        paths = command[1:]
        assert paths, "expected at least one workflow file to be scanned"
        workflows_prefix = str(tmp_path / ".github" / "workflows")
        assert all(p.startswith(workflows_prefix) for p in paths)

    def test_skips_when_actionlint_absent(self, tmp_path: Path) -> None:
        self._build_tree(tmp_path)
        with patch("scripts.validation.pre_pr.shutil.which", return_value=None):
            with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
                assert validate_workflow_yaml(tmp_path) is True
        mock_run.assert_not_called()


class TestValidateVendorPortability:
    """The vendor-portability gate wraps check_vendor_portability.py (#2050).

    Exit-code contract mirrored from the wrapped script:
    0 (no new offenders / no scan roots) -> pass, 1 (new offender) -> fail,
    2 (config error) -> fail. A missing wrapped script raises MissingScriptSkip.
    """

    def _make_repo(self, tmp_path: Path) -> Path:
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "check_vendor_portability.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        return tmp_path

    def test_passes_when_checker_exits_zero(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_run.return_value = (0, "[PASS] No new vendor-portability offenders.\n", "")
            assert validate_vendor_portability(repo) is True

    def test_fails_on_new_offender_exit_one(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_run.return_value = (1, "[FAIL] 1 new vendor-portability offender(s).\n", "")
            assert validate_vendor_portability(repo) is False

    def test_fails_on_config_error_exit_two(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_run.return_value = (2, "", "[FAIL] repo root not found")
            assert validate_vendor_portability(repo) is False

    def test_missing_script_raises_skip(self, tmp_path: Path) -> None:
        import pytest

        from scripts.validation.pre_pr import (
            MissingScriptSkip,
            validate_vendor_portability,
        )

        with pytest.raises(MissingScriptSkip):
            validate_vendor_portability(tmp_path)

    def test_passes_repo_root_to_checker(self, tmp_path: Path) -> None:
        from scripts.validation.pre_pr import validate_vendor_portability

        repo = self._make_repo(tmp_path)
        with patch("scripts.validation.pre_pr._run_subprocess") as mock_run:
            mock_run.return_value = (0, "", "")
            validate_vendor_portability(repo)

        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        repo_root_index = command.index("--repo-root")
        assert command[repo_root_index + 1] == str(repo)


# ---------------------------------------------------------------------------
# validate_review_marker  (Issue #1938)
# ---------------------------------------------------------------------------


class TestValidateReviewMarker:
    """Tests for the SHA-bound /review marker advisory check.

    Behavior contract:

    - Script missing, ``REVIEW_MARKER_ENFORCED`` unset / 0: returns ``True``
      (advisory skip; never blocks pre-PR).
    - Script missing, ``REVIEW_MARKER_ENFORCED=1``: returns ``False``.
    - Script present, HEAD has a binding marker: returns ``True`` regardless
      of enforcement.
    - Script present, HEAD has no marker, advisory: returns ``True``.
    - Script present, HEAD has no marker, enforced: returns ``False``.
    """

    import subprocess as _subprocess

    @staticmethod
    def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
        result = TestValidateReviewMarker._subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            input=stdin,
            check=True,
        )
        return result.stdout.strip()

    def _make_repo(self, tmp_path: Path, with_script: bool) -> Path:
        """Build a fake repo: real validator script (optionally) + git history."""
        repo = tmp_path / "repo"
        repo.mkdir()
        if with_script:
            dest = repo / "scripts" / "validation"
            dest.mkdir(parents=True)
            real = (
                Path(__file__).resolve().parent.parent
                / "scripts"
                / "validation"
                / "validate_review_marker.py"
            )
            (dest / "validate_review_marker.py").write_text(
                real.read_text(encoding="utf-8"), encoding="utf-8"
            )
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Tester")
        self._git(repo, "config", "commit.gpgsign", "false")
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "feat: one")
        (repo / "b.txt").write_text("y\n", encoding="utf-8")
        self._git(repo, "add", "b.txt")
        self._git(repo, "commit", "-q", "-m", "feat: two")
        return repo

    def _add_marker(self, repo: Path) -> None:
        """Add an empty /review marker commit binding the current tip."""
        tip = self._git(repo, "rev-parse", "HEAD")
        self._git(
            repo,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "review: marker",
            "--trailer",
            f"Reviewed-By: /review@analyst,security on {tip}",
        )

    def test_missing_script_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_missing_script_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=False)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_no_marker_advisory_returns_true(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_no_marker_enforced_returns_false(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is False

    def test_valid_marker_passes_advisory(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.delenv("REVIEW_MARKER_ENFORCED", raising=False)
        assert validate_review_marker(repo) is True

    def test_valid_marker_passes_enforced(
        self, tmp_path: Path, monkeypatch: Any  # noqa: ANN401
    ) -> None:
        repo = self._make_repo(tmp_path, with_script=True)
        self._add_marker(repo)
        monkeypatch.setenv("REVIEW_MARKER_ENFORCED", "1")
        assert validate_review_marker(repo) is True
