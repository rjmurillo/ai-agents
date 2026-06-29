#!/usr/bin/env python3
"""Tests for taste_lints module."""

from __future__ import annotations

import json
import os
import subprocess
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
get_diff_files = mod.get_diff_files
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

    def test_memory_data_file_exempt_despite_size(self) -> None:
        # .agents/memory/ holds append-only generated data (issue #2785).
        lines = ["{}\n"] * 9000
        result = check_file_size(
            ".agents/memory/causality/causal-graph.json", lines
        )
        assert result == []

    def test_memory_data_absolute_path_under_cwd_exempt(self, tmp_path: Path) -> None:
        # An absolute path that resolves under the repo root (cwd) is exempt.
        target = tmp_path / ".agents" / "memory" / "episodes" / "episode-1.json"
        lines = ["{}\n"] * 9000
        with patch.object(mod.Path, "cwd", return_value=tmp_path):
            result = check_file_size(str(target), lines)
        assert result == []

    def test_memory_segment_in_parent_dir_not_exempt(self, tmp_path: Path) -> None:
        # Security regression (gemini, PR #2786): a checkout whose PARENT dirs
        # contain .agents/memory must not leak the exemption to repo files.
        repo = tmp_path / ".agents" / "memory" / "repo"
        target = repo / "src" / "big_module.py"  # repo-relative is src/big_module.py
        lines = ["line\n"] * 600
        with patch.object(mod.Path, "cwd", return_value=repo):
            result = check_file_size(str(target), lines)
        assert len(result) == 1
        assert result[0].severity == "error"

    def test_absolute_path_outside_repo_not_exempt(self, tmp_path: Path) -> None:
        lines = ["{}\n"] * 9000
        result = check_file_size("/elsewhere/.agents/memory/data.json", lines)
        assert len(result) == 1
        assert result[0].severity == "error"

    def test_non_memory_large_file_still_fails(self) -> None:
        # A look-alike path that is not under .agents/memory must still fail.
        lines = ["line\n"] * 600
        result = check_file_size(".agents/memoryish/data.json", lines)
        assert len(result) == 1
        assert result[0].severity == "error"

    def test_memory_segment_mid_relative_path_not_exempt(self) -> None:
        # .agents/memory not anchored at the start of the relative path: not exempt.
        lines = ["line\n"] * 600
        result = check_file_size("src/.agents/memory/x.json", lines)
        assert len(result) == 1
        assert result[0].severity == "error"


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


def _run_git(repo: Path, *args: str) -> None:
    """Run a git command in the given repo, failing loudly on error."""
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )


def _make_repo_with_diff(repo: Path) -> None:
    """Create a git repo on a feature branch with one file changed vs main."""
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    (repo / "base.py").write_text("x = 1\n")
    _run_git(repo, "add", "base.py")
    _run_git(repo, "commit", "-m", "base")
    _run_git(repo, "checkout", "-b", "feature")
    (repo / "changed.py").write_text("y = 2\n")
    _run_git(repo, "add", "changed.py")
    _run_git(repo, "commit", "-m", "change")


class TestGetDiffFiles:
    """Tests for diff-scoped file selection (--diff-scope)."""

    def test_returns_only_changed_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        # Paths are anchored to the git root so they resolve from any cwd.
        assert len(result) == 1
        assert os.path.isabs(result[0])
        assert result[0].endswith("/changed.py")
        assert os.path.isfile(result[0])

    def test_returns_empty_when_no_changes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        _run_git(tmp_path, "checkout", "main")
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        assert result == []

    def test_returns_sorted_changed_files(self) -> None:
        # get_diff_files sorts for deterministic, mode-consistent output.
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="z.py\na.py\nm.py\n",
        )
        with patch.object(mod, "_git_root", return_value="/repo"), \
                patch.object(mod.subprocess, "run", return_value=completed):
            result = get_diff_files("main")
        assert result == ["/repo/a.py", "/repo/m.py", "/repo/z.py"]

    def test_raises_when_git_missing(self) -> None:
        with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError):
                get_diff_files("main")

    def test_raises_on_unknown_base(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # An unknown base makes git exit non-zero. That is a failure, not an
        # empty diff: returning [] would let a standards pre-flight pass without
        # linting. The function must surface the failure.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(RuntimeError):
            get_diff_files("does-not-exist")

    def test_rejects_dash_base(self) -> None:
        # CWE-88: a base starting with "-" would be parsed by git as an option.
        with pytest.raises(ValueError):
            get_diff_files("--output=/tmp/pwn")

    def test_rejects_empty_base(self) -> None:
        with pytest.raises(ValueError):
            get_diff_files("")

    def test_drops_traversal_paths(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="changed.py\n../escape.py\nfoo/../bar.py\n",
        )
        with patch.object(mod, "_git_root", return_value="/repo"), \
                patch.object(mod.subprocess, "run", return_value=completed):
            result = get_diff_files("main")
        assert result == ["/repo/changed.py"]


class TestMainDiffScope:
    """Tests for the --diff-scope main entry path."""

    def test_diff_scope_scans_only_changed_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        # Commit an oversized file on the base. A whole-tree scan would flag it,
        # but it is not in the feature diff so --diff-scope must ignore it. The
        # file is committed (not just left in the working tree) so the test
        # would catch a regression where scoping silently scans the whole tree.
        _run_git(tmp_path, "checkout", "main")
        (tmp_path / "legacy.py").write_text("x = 1\n" * 501)
        _run_git(tmp_path, "add", "legacy.py")
        _run_git(tmp_path, "commit", "-m", "oversized file on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_SUCCESS

    def test_diff_scope_flags_violation_in_changed_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        oversized = tmp_path / "changed.py"
        oversized.write_text("y = 2\n" * 501)
        _run_git(tmp_path, "add", "changed.py")
        _run_git(tmp_path, "commit", "-m", "grow")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS

    def test_diff_scope_unknown_base_returns_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # A git failure must surface as EXIT_ERROR, never a false EXIT_SUCCESS.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", "does-not-exist"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_dash_base_returns_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope=--bad"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_empty_base_returns_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # An empty base (e.g. ship/review passing "$BASE_BRANCH" while unset) must
        # error, not silently fall through to a full-repository scan.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", ""]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_catches_violation_from_subdirectory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Diff paths are repo-root-relative; anchoring them to the git root means
        # the lint still finds them when cwd is a subdirectory. Without the
        # anchor the file would be skipped and the gate would pass falsely.
        _make_repo_with_diff(tmp_path)
        oversized = tmp_path / "changed.py"
        oversized.write_text("y = 2\n" * 501)
        _run_git(tmp_path, "add", "changed.py")
        _run_git(tmp_path, "commit", "-m", "grow")
        subdir = tmp_path / "nested"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", "main"]):
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
