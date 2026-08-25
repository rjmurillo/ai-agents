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
classify_file_category = mod.classify_file_category
LintResult = mod.LintResult
Violation = mod.Violation
EXIT_SUCCESS = mod.EXIT_SUCCESS
EXIT_ERROR = mod.EXIT_ERROR
EXIT_VIOLATIONS = mod.EXIT_VIOLATIONS
get_diff_line_numbers = mod.get_diff_line_numbers
get_base_file_line_count = mod.get_base_file_line_count
_parse_hunk_header = mod._parse_hunk_header
_filter_violations_for_diff = mod._filter_violations_for_diff
_lint_file_rules = mod._lint_file_rules
has_suppression = mod.has_suppression
_suppression_window = mod._suppression_window


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
        result = check_file_size(".agents/memory/episodes/episode-batch.json", lines)
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

    def test_absolute_path_with_dotdot_escape_not_exempt(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        target = repo / ".agents" / "memory" / ".." / ".." / "src" / "big.py"
        lines = ["line\n"] * 600
        with patch.object(mod.Path, "cwd", return_value=repo):
            result = check_file_size(str(target), lines)
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

    def test_json_error_remediation_mentions_sharding_not_helper_functions(self) -> None:
        # JSON data files cannot have helper functions. Remediation must name
        # sharding or path exemption instead of module extraction. Issue #3970.
        lines = ["{}\n"] * 600
        result = check_file_size("data.json", lines)
        assert len(result) == 1
        assert result[0].severity == "error"
        assert "helper" not in result[0].remediation.lower()
        assert "type definitions" not in result[0].remediation.lower()
        assert "shard" in result[0].remediation.lower()

    def test_json_warning_remediation_mentions_exemption_not_helper_functions(self) -> None:
        # Warning-range JSON files also get the data-file remediation. Issue #3970.
        lines = ["{}\n"] * 400
        result = check_file_size("metrics.json", lines)
        assert len(result) == 1
        assert result[0].severity == "warning"
        assert "helper" not in result[0].remediation.lower()
        assert "exempt" in result[0].remediation.lower()

    def test_yaml_error_remediation_is_data_file_advice(self) -> None:
        # .yml data files get the same data-file remediation. Issue #3970.
        lines = ["key: val\n"] * 600
        result = check_file_size("config.yml", lines)
        assert len(result) == 1
        assert "shard" in result[0].remediation.lower()

    def test_python_error_remediation_still_names_helpers(self) -> None:
        # Non-data files retain the existing module-extraction advice.
        lines = ["x = 1\n"] * 600
        result = check_file_size("src/big_module.py", lines)
        assert len(result) == 1
        assert "big_module_helpers.py" in result[0].remediation


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

    def test_leading_underscore_private_module_passes(self) -> None:
        # PEP 8 private module; the directory convention in scripts/eval/. #2795.
        result = check_naming("scripts/eval/_run_rollup_core.py", [])
        assert [v for v in result if v.rule == "naming"] == []

    def test_leading_underscore_then_pascal_case_still_fails(self) -> None:
        # The optional underscore precedes snake_case only; _Pascal is not valid.
        result = check_naming("src/_MyModule.py", [])
        naming_violations = [v for v in result if v.rule == "naming"]
        assert len(naming_violations) >= 1
        assert "snake_case" in naming_violations[0].message

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

    def test_hook_leading_underscore_helper_exempt(self) -> None:
        # Private helper module in the hooks tree; not an entrypoint. #3239.
        result = check_naming(".claude/hooks/PreToolUse/_bootstrap.py", [])
        assert [v for v in result if v.rule == "naming"] == []

    def test_hook_base_module_exempt(self) -> None:
        # Shared framework base class (*_base.py); not an entrypoint. #3239.
        result = check_naming(".claude/hooks/PreToolUse/push_guard_base.py", [])
        assert [v for v in result if v.rule == "naming"] == []

    def test_hook_exemption_does_not_suppress_python_naming(self) -> None:
        # The invoke_ exemption is scoped to the hook-naming rule. A leading
        # underscore silences hook naming but must not mask a bad Python name:
        # _BadName is not valid snake_case, so python naming still flags it. #3239.
        result = check_naming(".claude/hooks/PreToolUse/_BadName.py", [])
        naming_violations = [v for v in result if v.rule == "naming"]
        assert len(naming_violations) == 1
        assert "snake_case" in naming_violations[0].message

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

    def test_generated_matcher_shim_is_skipped(self, tmp_path: Path) -> None:
        generated = tmp_path / "invoke_guard__Bash_123.py"
        generated.write_text(
            "# AUTO-GENERATED MATCHER SHIM (REQ-003-007)\n" + "x = 1\n" * 600,
            encoding="utf-8",
        )

        result = run_lint([str(generated)], ("file-size",))

        assert result.files_scanned == 1
        assert result.files_by_category == {"generated": 1}
        assert result.violations == []

    def test_classifies_test_files(self) -> None:
        assert classify_file_category("tests/test_example.py", []) == "test"

    def test_marker_below_header_window_is_authored(self) -> None:
        # A marker string that appears only past the header window must NOT
        # reclassify an authored file (for example a generator script) as
        # generated.
        lines = [f"# line {n}\n" for n in range(30)]
        lines.append('_MARKERS = ("DO NOT EDIT BY HAND - regenerated",)\n')
        assert classify_file_category("build/scripts/generate_x.py", lines) == "authored"

    def test_marker_in_header_window_is_generated(self) -> None:
        lines = ["#!/usr/bin/env python3\n", "# GENERATED -- DO NOT EDIT\n"]
        assert classify_file_category("scripts/shim.py", lines) == "generated"

    def test_github_instructions_path_is_generated(self) -> None:
        # .github/instructions/*.instructions.md are generated mirrors of
        # .claude/rules/* and carry no in-file markers; classify by path.
        assert (
            classify_file_category(".github/instructions/universal.instructions.md", [])
            == "generated"
        )

    def test_classify_ignores_checkout_path_segments(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: a clone whose checkout directory itself contains a
        # generated segment (e.g. .../src/copilot-cli/...) must not misclassify
        # authored files as generated. classify uses CWD-relative parts.
        checkout = tmp_path / "src" / "copilot-cli" / "clone"
        authored = checkout / "pkg" / "module.py"
        authored.parent.mkdir(parents=True)
        authored.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.chdir(checkout)

        # Absolute path under the checkout: relative parts are pkg/module.py.
        assert classify_file_category(str(authored), ["x = 1\n"]) == "authored"
        # A genuinely repo-relative generated path is still caught.
        assert classify_file_category("src/copilot-cli/skill.py", []) == "generated"

    def test_classify_anchors_generated_segments_at_repo_root(self) -> None:
        # Regression: _GENERATED_PATH_SEGMENTS are repo-root-anchored, so a
        # repo-relative path carrying a segment at a non-root position (a
        # vendored or fixture dir) must not be misclassified as generated.
        assert classify_file_category("vendor/pkg/src/copilot-cli/lib.py", []) == "authored"
        # The genuine repo-root mirror is still classified generated.
        assert classify_file_category("src/copilot-cli/skills/x.py", []) == "generated"

    def test_classify_uses_git_root_not_cwd_for_absolute_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: get_diff_files anchors diff paths to the git root (absolute)
        # so they resolve from any working directory. Classification must
        # relativize against that root, not CWD. Run from a subdirectory deeper
        # than the root: a CWD-relative match would raise ValueError, fall back to
        # the full absolute parts, and misclassify the mirror as authored.
        repo_root = tmp_path / "repo"
        generated = repo_root / "src" / "copilot-cli" / "skills" / "x" / "shim.py"
        generated.parent.mkdir(parents=True)
        generated.write_text("x = 1\n", encoding="utf-8")
        subdir = repo_root / "tests" / "deep"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        monkeypatch.setattr(mod, "_git_root_for_cwd", lambda _cwd: str(repo_root))

        assert classify_file_category(str(generated), []) == "generated"

    def test_run_lint_skips_generated_by_path_without_reading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # run_lint must classify path-generated files (mirrors) without reading
        # them. Patch read_file_lines to raise so any read would fail the test.
        monkeypatch.chdir(tmp_path)
        mirror = tmp_path / "src" / "copilot-cli" / "skills" / "x" / "shim.py"
        mirror.parent.mkdir(parents=True)
        mirror.write_text("x = 1\n" * 600, encoding="utf-8")

        def _boom(_path: str) -> list[str]:
            raise AssertionError("read_file_lines must not run for path-generated files")

        monkeypatch.setattr(mod, "read_file_lines", _boom)
        result = run_lint([str(mirror)], ("file-size",))

        assert result.files_scanned == 1
        assert result.files_by_category == {"generated": 1}
        assert result.violations == []

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
            violations=[
                Violation(
                    rule="file-size",
                    severity="error",
                    file="test.py",
                    line=501,
                    message="File exceeds 500 lines",
                    remediation="AGENT_REMEDIATION: Split this file",
                )
            ],
        )
        output = format_text(result)
        assert "AGENT_REMEDIATION" in output
        assert "[ERROR]" in output


class TestFormatJson:
    """Tests for JSON formatting."""

    def test_json_output_structure(self) -> None:
        result = LintResult(
            files_scanned=1,
            violations=[
                Violation(
                    rule="naming",
                    severity="warning",
                    file="test.py",
                    line=0,
                    message="Bad name",
                    remediation="Fix it",
                )
            ],
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

    def test_returns_only_changed_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        # Paths are anchored to the git root so they resolve from any cwd.
        assert len(result) == 1
        assert os.path.isabs(result[0])
        assert result[0].endswith("/changed.py")
        assert os.path.isfile(result[0])

    def test_returns_empty_when_no_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        _run_git(tmp_path, "checkout", "main")
        monkeypatch.chdir(tmp_path)
        result = get_diff_files("main")
        assert result == []

    def test_returns_sorted_changed_files(self) -> None:
        # get_diff_files sorts for deterministic, mode-consistent output.
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="z.py\na.py\nm.py\n",
        )
        with (
            patch.object(mod, "_git_root", return_value="/repo"),
            patch.object(mod.subprocess, "run", return_value=completed),
        ):
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
            args=[],
            returncode=0,
            stdout="changed.py\n../escape.py\nfoo/../bar.py\n",
        )
        with (
            patch.object(mod, "_git_root", return_value="/repo"),
            patch.object(mod.subprocess, "run", return_value=completed),
        ):
            result = get_diff_files("main")
        assert result == ["/repo/changed.py"]


class TestMainDiffScope:
    """Tests for the --diff-scope main entry path."""

    def test_diff_scope_scans_only_changed_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

    def test_diff_scope_flags_violation_in_changed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        oversized = tmp_path / "changed.py"
        oversized.write_text("y = 2\n" * 501)
        _run_git(tmp_path, "add", "changed.py")
        _run_git(tmp_path, "commit", "-m", "grow")
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", "main"]):
            result = main()
        assert result == EXIT_VIOLATIONS

    def test_diff_scope_unknown_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A git failure must surface as EXIT_ERROR, never a false EXIT_SUCCESS.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", "does-not-exist"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_dash_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope=--bad"]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_empty_base_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An empty base (e.g. ship/review passing "$BASE_BRANCH" while unset) must
        # error, not silently fall through to a full-repository scan.
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["taste_lints.py", "--diff-scope", ""]):
            result = main()
        assert result == EXIT_ERROR

    def test_diff_scope_catches_violation_from_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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


class TestParseHunkHeaderTasteLints:
    """Unit tests for _parse_hunk_header in taste_lints."""

    def test_standard_hunk(self) -> None:
        start, count = _parse_hunk_header("@@ -1,3 +1,4 @@")
        assert start == 1
        assert count == 4

    def test_implicit_single_line(self) -> None:
        start, count = _parse_hunk_header("@@ -5 +5 @@")
        assert start == 5
        assert count == 1

    def test_no_match(self) -> None:
        start, count = _parse_hunk_header("not a header")
        assert start == 0
        assert count == 0


class TestGetDiffLineNumbersTasteLints:
    """Unit tests for get_diff_line_numbers in taste_lints."""

    def test_empty_base_returns_empty_dict(self) -> None:
        result = get_diff_line_numbers("")
        assert result == {}

    def test_parses_added_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_repo_with_diff(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = get_diff_line_numbers("main")
        assert len(result) == 1
        key = next(iter(result))
        assert key.endswith("changed.py")
        assert 1 in result[key]

    def test_traversal_path_excluded(self) -> None:
        diff_text = (
            "diff --git a/../escape.py b/../escape.py\n"
            "--- a/../escape.py\n"
            "+++ b/../escape.py\n"
            "@@ -0,0 +1 @@\n"
            "+bad\n"
        )
        with (
            patch.object(mod, "_git_root", return_value="/repo"),
            patch.object(mod, "_run_git_diff", return_value=diff_text),
        ):
            result = get_diff_line_numbers("main")
        assert result == {}


class TestGetBaseFileLineCount:
    """Tests for get_base_file_line_count."""

    def test_counts_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("a\nb\nc\n")
        assert get_base_file_line_count(str(f)) == 3

    def test_missing_file_returns_zero(self) -> None:
        assert get_base_file_line_count("/does/not/exist.py") == 0

    def test_empty_file_returns_zero(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        assert get_base_file_line_count(str(f)) == 0


class TestFilterViolationsForDiff:
    """Unit tests for _filter_violations_for_diff."""

    def _v(self, line: int) -> object:
        return Violation(
            rule="file-size",
            severity="warning",
            file="/repo/f.py",
            line=line,
            message="msg",
            remediation="fix",
        )

    def test_file_not_in_diff_returns_empty(self) -> None:
        v = self._v(10)
        result = _filter_violations_for_diff([v], "/repo/f.py", {}, "main")
        assert result == []

    def test_line_in_diff_kept(self) -> None:
        v = self._v(5)
        result = _filter_violations_for_diff([v], "/repo/f.py", {"/repo/f.py": {5, 6}}, "main")
        assert result == [v]

    def test_line_not_in_diff_suppressed(self) -> None:
        v = self._v(99)
        result = _filter_violations_for_diff(
            [v], "/repo/f.py", {"/repo/f.py": {1, 2, 3}}, "main"
        )
        assert result == []

    def test_isolating_negative_control_diff_lines_param(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Removing diff_lines from run_lint causes pre-existing violations to appear.

        This is the isolating negative control: proves diff_lines is
        individually load-bearing.  If run_lint accepted diff_lines but ignored
        it, this test would still pass -- meaning a survivor here indicates the
        parameter is not wired up.
        """
        _make_repo_with_diff(tmp_path)
        # Add a large file pre-existing on main
        lines = ["x = 1\n"] * 600
        (tmp_path / "big.py").write_text("".join(lines))
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "big.py")
        _run_git(tmp_path, "commit", "-m", "big file on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)

        big = str(tmp_path / "big.py")
        # Without diff filtering: big.py triggers file-size violation
        result_no_filter = run_lint([big], ("file-size",), diff_lines=None)
        assert any(v.file == big for v in result_no_filter.violations), (
            "without filtering, big.py file-size violation must be present"
        )


class TestDiffScopeLineFilteringTasteLints:
    """Integration tests: pre-existing lint violations are suppressed in diff mode."""

    def test_preexisting_file_size_violation_suppressed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A large file on main not in the diff must not produce a file-size violation."""
        _make_repo_with_diff(tmp_path)
        lines = ["x = 1\n"] * 600
        (tmp_path / "big.py").write_text("".join(lines))
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "big.py")
        _run_git(tmp_path, "commit", "-m", "big file on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        monkeypatch.chdir(tmp_path)

        diff_lines = get_diff_line_numbers("main")
        files = get_diff_files("main")
        result = run_lint(files, ("file-size",), diff_lines=diff_lines, diff_base="main")
        big = str(tmp_path / "big.py")
        assert big not in [v.file for v in result.violations], (
            "pre-existing big.py file-size violation must be suppressed"
        )

    def test_new_complexity_violation_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A complexity violation introduced in the diff must still be flagged."""
        _make_repo_with_diff(tmp_path)
        # Write a complex function that will trigger check_complexity
        complex_code = "def f(x):\n"
        for i in range(12):
            complex_code += f"    if x == {i}:\n        return {i}\n"
        complex_code += "    return -1\n"
        (tmp_path / "complex.py").write_text(complex_code)
        _run_git(tmp_path, "add", "complex.py")
        _run_git(tmp_path, "commit", "-m", "add complex function")
        monkeypatch.chdir(tmp_path)

        diff_lines = get_diff_line_numbers("main")
        files = get_diff_files("main")
        result = run_lint(files, ("complexity",), diff_lines=diff_lines, diff_base="main")
        added = str(tmp_path / "complex.py")
        assert any(v.file == added for v in result.violations), (
            "complexity violation on a changed file must still be reported"
        )

    def test_preexisting_complexity_on_unchanged_line_suppressed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A complexity violation on a line NOT in the diff must be suppressed.

        This is the isolating negative control for _filter_violations_for_diff.
        The complex function lives at line 1 of the file (pre-existing on main).
        The feature branch adds a comment at a high line number, making the file
        appear in get_diff_files, but the diff_lines set does NOT include line 1.
        The complexity violation must therefore be suppressed.
        """
        # Build a complex function at line 1 on main
        complex_code = "def f(x):\n"
        for i in range(12):
            complex_code += f"    if x == {i}:\n        return {i}\n"
        complex_code += "    return -1\n"
        # Pad to make the file long enough that we can add a line at the end
        padding = "# pad\n" * 50
        content = complex_code + padding
        _make_repo_with_diff(tmp_path)
        (tmp_path / "complex.py").write_text(content)
        _run_git(tmp_path, "checkout", "main")
        _run_git(tmp_path, "add", "complex.py")
        _run_git(tmp_path, "commit", "-m", "complex function on main")
        _run_git(tmp_path, "checkout", "feature")
        _run_git(tmp_path, "rebase", "main")
        # Add one comment at the very end (high line) -- this is the ONLY change
        appended = content + "# new comment added by feature\n"
        (tmp_path / "complex.py").write_text(appended)
        _run_git(tmp_path, "add", "complex.py")
        _run_git(tmp_path, "commit", "-m", "add comment at end")
        monkeypatch.chdir(tmp_path)

        diff_lines = get_diff_line_numbers("main")
        files = get_diff_files("main")
        # complex.py IS in the diff (it changed), but line 1 is NOT in diff_lines
        assert any(f.endswith("complex.py") for f in files), "complex.py must be in diff"
        cplx = str(tmp_path / "complex.py")
        assert cplx in diff_lines, "complex.py must be in diff_lines"
        assert 1 not in diff_lines[cplx], "line 1 must NOT be in changed set"

        result = run_lint(files, ("complexity",), diff_lines=diff_lines, diff_base="main")
        assert not any(v.file == cplx for v in result.violations), (
            "pre-existing complexity violation on unchanged line 1 must be suppressed"
        )


class TestSuppressionSurvivesFrontmatter:
    """A suppression must be findable on a file carrying YAML frontmatter.

    ADR-073 lifecycle frontmatter is exactly 10 lines, which is the whole
    suppression window. ADR-035 lost a working `file-size` suppression this way
    during the issue #5190 backfill.
    """

    FM = [
        "---\n", "id: ADR-035\n", "status: accepted\n", "date: 2025-12-30\n",
        "decision-makers: [rjmurillo]\n", "supersedes: []\n",
        "superseded-by: null\n", "explainer: null\n", "implemented: true\n",
        "---\n",
    ]
    SUPPRESSION = "<!-- # taste-lint: ignore file-size (prose ADR) -->\n"

    def test_suppression_found_after_frontmatter(self) -> None:
        lines = [*self.FM, "\n", "# ADR-035: Title\n", "\n", self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is True

    def test_suppression_still_found_without_frontmatter(self) -> None:
        lines = ["# ADR-035: Title\n", "\n", self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is True

    def test_absent_suppression_still_reports_false(self) -> None:
        lines = [*self.FM, "\n", "# ADR-035: Title\n", "\n", "Body text.\n"]

        assert has_suppression(lines, "file-size") is False

    def test_suppression_for_a_different_rule_does_not_match(self) -> None:
        lines = [*self.FM, "<!-- # taste-lint: ignore long-function -->\n"]

        assert has_suppression(lines, "file-size") is False

    def test_suppression_far_below_frontmatter_is_still_out_of_window(self) -> None:
        lines = [*self.FM, *["filler\n"] * 11, self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is False

    def test_unterminated_frontmatter_does_not_widen_the_window(self) -> None:
        # A leading `---` with no closing delimiter is a horizontal rule, not
        # frontmatter, so the window stays at 10 lines. The suppression sits
        # past line 10 on purpose: on line 2 it would fall inside both the
        # correct window and a buggy to-EOF one, and the test could not fail.
        lines = ["---\n", *["filler\n"] * 12, self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is False

    def test_a_horizontal_rule_pair_is_not_frontmatter(self) -> None:
        # The regression Copilot found: a doc opening with a horizontal rule and
        # carrying an unrelated `---` separator far below. Accepting any second
        # `---` as the terminator widened the window to that separator and
        # disabled a lint hundreds of lines from any real suppression. The body
        # between the delimiters is prose, not a YAML mapping.
        lines = ["---\n", "# Title\n", *["filler\n"] * 300, "---\n", self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is False

    def test_frontmatter_scalar_body_is_not_a_mapping(self) -> None:
        # Parses as YAML, but as a string rather than a mapping. Not frontmatter.
        lines = ["---\n", "just a sentence\n", "---\n", *["filler\n"] * 9, self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is False

    def test_mapping_shaped_but_malformed_yaml_still_counts_as_frontmatter(self) -> None:
        # `key: [unclosed` would fail a real YAML parse, but between two `---`
        # at the top of a file it is frontmatter the author got wrong, not a
        # horizontal rule. The window is deciding which of those two things it
        # is looking at, and a broken value does not make it prose.
        lines = ["---\n", "key: [unclosed\n", "---\n", *["filler\n"] * 9, self.SUPPRESSION]

        assert has_suppression(lines, "file-size") is True

    def test_prose_with_a_colon_is_not_a_mapping(self) -> None:
        # The discriminator is shape, so a sentence that happens to contain a
        # colon must still be rejected: its key half is not a bare key.
        lines = [
            "---\n",
            "Note: this document was written on a Tuesday, see below\n",
            "and it continues without indentation\n",
            "---\n",
            *["filler\n"] * 9,
            self.SUPPRESSION,
        ]

        assert has_suppression(lines, "file-size") is False

    def test_empty_file_is_safe(self) -> None:
        assert has_suppression([], "file-size") is False

    def test_suppression_inside_the_frontmatter_still_counts(self) -> None:
        # ADR-068 and ADR-085 put it on line 2, as a YAML comment. Widening the
        # window must not retire that placement.
        lines = [
            "---\n",
            "# taste-lint: ignore file-size, accepted append-only record.\n",
            *self.FM[1:],
            "# ADR-068: Title\n",
        ]

        assert has_suppression(lines, "file-size") is True

    def test_window_covers_frontmatter_plus_ten_content_lines(self) -> None:
        lines = [*self.FM, *["filler\n"] * 9, self.SUPPRESSION]

        assert _suppression_window(lines)[-1] == self.SUPPRESSION
        assert has_suppression(lines, "file-size") is True

    def test_window_is_ten_lines_without_a_block(self) -> None:
        lines = ["# Title\n", "body\n"]

        assert _suppression_window(lines) == lines
