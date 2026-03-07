#!/usr/bin/env python3
"""Tests for taste_lints module."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/taste-lints/scripts/taste_lints.py")
check_file_size = mod.check_file_size
check_naming = mod.check_naming
check_complexity = mod.check_complexity
check_skill_size = mod.check_skill_size
run_lint = mod.run_lint
format_text = mod.format_text
format_json = mod.format_json
parse_rules = mod.parse_rules
main = mod.main
is_safe_path = mod.is_safe_path
LintResult = mod.LintResult
Violation = mod.Violation
EXIT_SUCCESS = mod.EXIT_SUCCESS
EXIT_ERROR = mod.EXIT_ERROR
EXIT_VIOLATIONS = mod.EXIT_VIOLATIONS


class TestCheckFileSize:
    """Tests for file size checking."""

    def test_small_file_no_violation(self) -> None:
        lines = ["line\n"] * 100
        result = check_file_size("test.py", lines)
        assert result == []

    def test_warning_at_301_lines(self) -> None:
        lines = ["line\n"] * 301
        result = check_file_size("test.py", lines)
        assert len(result) == 1
        assert result[0].severity == "warning"
        assert result[0].rule == "file-size"
        assert "301/500" in result[0].message

    def test_error_at_501_lines(self) -> None:
        lines = ["line\n"] * 501
        result = check_file_size("test.py", lines)
        assert len(result) == 1
        assert result[0].severity == "error"
        assert "AGENT_REMEDIATION" in result[0].remediation

    def test_suppression_skips_check(self) -> None:
        lines = ["# taste-lint: ignore file-size\n"] + ["line\n"] * 600
        result = check_file_size("test.py", lines)
        assert result == []

    def test_remediation_includes_basename(self) -> None:
        lines = ["line\n"] * 501
        result = check_file_size("src/my_module.py", lines)
        assert "my_module_helpers.py" in result[0].remediation


class TestCheckNaming:
    """Tests for naming convention checks."""

    def test_snake_case_python_passes(self) -> None:
        result = check_naming("src/my_module.py", [])
        assert result == []

    def test_non_snake_case_python_fails(self) -> None:
        result = check_naming("src/MyModule.py", [])
        naming_violations = [v for v in result if v.rule == "naming"]
        assert len(naming_violations) >= 1
        assert naming_violations[0].severity == "error"
        assert "snake_case" in naming_violations[0].message

    def test_init_file_passes(self) -> None:
        result = check_naming("src/__init__.py", [])
        assert result == []

    def test_kebab_case_yaml_passes(self) -> None:
        result = check_naming("config/my-config.yml", [])
        assert result == []

    def test_hook_without_invoke_prefix_fails(self) -> None:
        result = check_naming(".claude/hooks/PreToolUse/my_guard.py", [])
        naming_violations = [v for v in result if v.rule == "naming"]
        hook_violations = [v for v in naming_violations if "invoke_" in v.remediation]
        assert len(hook_violations) == 1

    def test_hook_with_invoke_prefix_passes(self) -> None:
        result = check_naming(".claude/hooks/PreToolUse/invoke_my_guard.py", [])
        hook_violations = [v for v in result if "invoke_" in v.message]
        assert hook_violations == []

    def test_suppression_skips_naming(self) -> None:
        lines = ["# taste-lint: ignore naming\n"]
        result = check_naming("src/BadName.py", lines)
        assert result == []

    def test_skill_directory_kebab_case_passes(self) -> None:
        result = check_naming(".claude/skills/my-skill/scripts/helper.py", [])
        skill_violations = [v for v in result if "Skill directory" in v.message]
        assert skill_violations == []


class TestCheckComplexity:
    """Tests for function complexity checking."""

    def test_simple_function_passes(self) -> None:
        code = textwrap.dedent("""\
            def simple():
                if True:
                    pass
                return 1
        """)
        result = check_complexity("test.py", code.splitlines(keepends=True))
        assert result == []

    def test_complex_function_fails(self) -> None:
        branches = "\n".join(f"    if x == {i}:\n        pass" for i in range(12))
        code = f"def complex_func():\n{branches}\n"
        result = check_complexity("test.py", code.splitlines(keepends=True))
        assert len(result) == 1
        assert result[0].severity == "error"
        assert "complex_func" in result[0].message
        assert "AGENT_REMEDIATION" in result[0].remediation

    def test_non_python_files_skipped(self) -> None:
        result = check_complexity("test.sh", ["if x; then\n"] * 20)
        assert result == []

    def test_suppression_skips_complexity(self) -> None:
        branches = "\n".join(f"    if x == {i}:\n        pass" for i in range(12))
        code = f"# taste-lint: ignore complexity\ndef complex_func():\n{branches}\n"
        result = check_complexity("test.py", code.splitlines(keepends=True))
        assert result == []


class TestCheckSkillSize:
    """Tests for skill SKILL.md size checking."""

    def test_small_skill_passes(self) -> None:
        lines = ["---\n", "name: test\n", "---\n"] + ["content\n"] * 50
        result = check_skill_size(".claude/skills/test/SKILL.md", lines)
        assert result == []

    def test_large_skill_warns(self) -> None:
        lines = ["---\n", "name: test\n", "---\n"] + ["content\n"] * 310
        result = check_skill_size(".claude/skills/test/SKILL.md", lines)
        assert len(result) == 1
        assert result[0].severity == "warning"

    def test_oversized_skill_errors(self) -> None:
        lines = ["---\n", "name: test\n", "---\n"] + ["content\n"] * 510
        result = check_skill_size(".claude/skills/test/SKILL.md", lines)
        assert len(result) == 1
        assert result[0].severity == "error"
        assert "AGENT_REMEDIATION" in result[0].remediation

    def test_size_exception_skips(self) -> None:
        lines = ["---\n", "name: test\n", "size-exception: true\n", "---\n"] + ["x\n"] * 600
        result = check_skill_size(".claude/skills/test/SKILL.md", lines)
        assert result == []

    def test_non_skill_file_skipped(self) -> None:
        lines = ["content\n"] * 600
        result = check_skill_size("src/README.md", lines)
        assert result == []


class TestRunLint:
    """Tests for the run_lint function."""

    def test_lint_with_all_rules(self, tmp_path: Path) -> None:
        test_file = tmp_path / "good_file.py"
        test_file.write_text("x = 1\n")
        result = run_lint([str(test_file)], ("file-size", "naming", "complexity"))
        assert result.files_scanned == 1
        assert result.error_count == 0

    def test_lint_skips_non_scannable(self, tmp_path: Path) -> None:
        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"\x89PNG")
        result = run_lint([str(test_file)], ("file-size",))
        assert result.files_scanned == 0

    def test_lint_skips_missing_files(self) -> None:
        result = run_lint(["/nonexistent/file.py"], ("file-size",))
        assert result.files_scanned == 0


class TestFormatText:
    """Tests for text formatting."""

    def test_no_violations_message(self) -> None:
        result = LintResult(files_scanned=5)
        output = format_text(result)
        assert "no violations found" in output
        assert "5 files scanned" in output

    def test_violations_include_remediation(self) -> None:
        result = LintResult(
            files_scanned=1,
            violations=[Violation(
                rule="file-size",
                severity="error",
                file="test.py",
                line=501,
                message="File exceeds 500 lines",
                remediation="AGENT_REMEDIATION: Split this file",
            )],
        )
        output = format_text(result)
        assert "AGENT_REMEDIATION" in output
        assert "[ERROR]" in output


class TestFormatJson:
    """Tests for JSON formatting."""

    def test_json_output_structure(self) -> None:
        result = LintResult(
            files_scanned=1,
            violations=[Violation(
                rule="naming",
                severity="warning",
                file="test.py",
                line=0,
                message="Bad name",
                remediation="Fix it",
            )],
        )
        data = json.loads(format_json(result))
        assert data["files_scanned"] == 1
        assert data["warning_count"] == 1
        assert len(data["violations"]) == 1
        assert data["violations"][0]["remediation"] == "Fix it"


class TestParseRules:
    """Tests for rule parsing."""

    def test_empty_returns_all(self) -> None:
        result = parse_rules("")
        assert result == ("file-size", "naming", "complexity", "skill-size")

    def test_single_rule(self) -> None:
        result = parse_rules("file-size")
        assert result == ("file-size",)

    def test_multiple_rules(self) -> None:
        result = parse_rules("file-size,naming")
        assert result == ("file-size", "naming")

    def test_invalid_rule_exits(self) -> None:
        with pytest.raises(SystemExit):
            parse_rules("invalid-rule")


class TestMain:
    """Tests for the main entry point."""

    def test_no_args_returns_error(self) -> None:
        with patch("sys.argv", ["taste_lints.py"]):
            result = main()
        assert result == EXIT_ERROR

    def test_staged_no_files(self) -> None:
        with (
            patch("sys.argv", ["taste_lints.py", "--git-staged"]),
            patch.object(mod, "get_staged_files", return_value=[]),
        ):
            result = main()
        assert result == EXIT_SUCCESS

    def test_file_args_clean(self, tmp_path: Path) -> None:
        test_file = tmp_path / "clean.py"
        test_file.write_text("x = 1\n")
        with patch("sys.argv", ["taste_lints.py", str(test_file)]):
            result = main()
        assert result == EXIT_SUCCESS

    def test_file_with_violations(self, tmp_path: Path) -> None:
        test_file = tmp_path / "big_file.py"
        test_file.write_text("x = 1\n" * 501)
        with patch("sys.argv", ["taste_lints.py", str(test_file)]):
            result = main()
        assert result == EXIT_VIOLATIONS


class TestIsSafePath:
    """Tests for path traversal prevention (CWE-22)."""

    def test_absolute_path_allowed(self) -> None:
        assert is_safe_path("/usr/local/bin/script.py") is True

    def test_relative_path_without_traversal_allowed(self) -> None:
        assert is_safe_path("src/module.py") is True
        assert is_safe_path("./src/module.py") is True

    def test_relative_path_with_traversal_rejected(self) -> None:
        assert is_safe_path("../secrets.py") is False
        assert is_safe_path("foo/../bar.py") is False
        assert is_safe_path("foo/bar/../baz.py") is False

    def test_simple_filename_allowed(self) -> None:
        assert is_safe_path("script.py") is True

    def test_run_lint_skips_unsafe_paths(self, tmp_path: Path) -> None:
        # Create a real file
        safe_file = tmp_path / "safe.py"
        safe_file.write_text("x = 1\n")
        # Run lint with both safe and unsafe paths
        files = [str(safe_file), "../unsafe.py", "foo/../bar.py"]
        result = run_lint(files, ("file-size",))
        # Only the safe file should be scanned
        assert result.files_scanned == 1
