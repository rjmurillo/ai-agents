#!/usr/bin/env python3
"""Tests for get_applicable_steering module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/steering-matcher/get_applicable_steering.py")
glob_to_regex = mod.glob_to_regex
file_matches_pattern = mod.file_matches_pattern
get_applicable_steering = mod.get_applicable_steering
main = mod.main


class TestGlobToRegex:
    """Tests for glob_to_regex function."""

    def test_simple_wildcard(self) -> None:
        regex = glob_to_regex("*.md")
        assert regex == "^[^/]*\\.md$"

    def test_globstar_slash(self) -> None:
        regex = glob_to_regex("**/*.md")
        import re
        assert re.match(regex, "docs/file.md")
        assert re.match(regex, "a/b/c/file.md")

    def test_question_mark(self) -> None:
        regex = glob_to_regex("file?.md")
        import re
        assert re.match(regex, "file1.md")
        assert not re.match(regex, "file12.md")

    def test_dot_escaped(self) -> None:
        regex = glob_to_regex("*.ts")
        import re
        assert re.match(regex, "app.ts")
        assert not re.match(regex, "appts")

    def test_slash_globstar(self) -> None:
        regex = glob_to_regex("src/**")
        import re
        assert re.match(regex, "src/a/b/c")

    def test_exact_match(self) -> None:
        regex = glob_to_regex("Makefile")
        import re
        assert re.match(regex, "Makefile")
        assert not re.match(regex, "NotMakefile")


class TestFileMatchesPattern:
    """Tests for file_matches_pattern function."""

    def test_matches_simple_pattern(self) -> None:
        assert file_matches_pattern("src/app.ts", ["src/*.ts"]) is True

    def test_matches_globstar(self) -> None:
        assert file_matches_pattern("src/deep/nested/file.py", ["**/*.py"]) is True

    def test_no_match(self) -> None:
        assert file_matches_pattern("src/app.ts", ["*.py"]) is False

    def test_normalizes_backslashes(self) -> None:
        assert file_matches_pattern("src\\app.ts", ["src/*.ts"]) is True

    def test_matches_any_of_multiple_patterns(self) -> None:
        assert file_matches_pattern("docs/README.md", ["src/*.ts", "docs/*.md"]) is True

    def test_empty_patterns(self) -> None:
        assert file_matches_pattern("file.py", []) is False


class TestGetApplicableSteering:
    """Tests for get_applicable_steering function."""

    @pytest.fixture
    def steering_dir(self, tmp_path: Path) -> Path:
        sdir = tmp_path / "steering"
        sdir.mkdir()
        return sdir

    def test_returns_empty_for_no_files(self, steering_dir: Path) -> None:
        result = get_applicable_steering([], str(steering_dir))
        assert result == []

    def test_returns_empty_for_missing_dir(self) -> None:
        result = get_applicable_steering(["src/app.py"], "/nonexistent/path")
        assert result == []

    def test_matches_steering_file(self, steering_dir: Path) -> None:
        (steering_dir / "auth-review.md").write_text(
            '---\napplyTo: "src/Auth/**"\npriority: 10\n---\n\nAuth steering.\n'
        )
        result = get_applicable_steering(["src/Auth/login.py"], str(steering_dir))
        assert len(result) == 1
        assert result[0]["Name"] == "auth-review"
        assert result[0]["Priority"] == 10

    def test_excludes_readme(self, steering_dir: Path) -> None:
        (steering_dir / "README.md").write_text(
            '---\napplyTo: "**"\npriority: 1\n---\n\nReadme.\n'
        )
        result = get_applicable_steering(["anything.py"], str(steering_dir))
        assert len(result) == 0

    def test_excludes_skill_md(self, steering_dir: Path) -> None:
        (steering_dir / "SKILL.md").write_text(
            '---\napplyTo: "**"\npriority: 1\n---\n\nSkill.\n'
        )
        result = get_applicable_steering(["anything.py"], str(steering_dir))
        assert len(result) == 0

    def test_respects_exclude_from(self, steering_dir: Path) -> None:
        (steering_dir / "all-code.md").write_text(
            '---\napplyTo: "**/*.py"\nexcludeFrom: "tests/**"\npriority: 5\n---\n\nCode steering.\n'
        )
        result = get_applicable_steering(["tests/test_app.py"], str(steering_dir))
        assert len(result) == 0

        result = get_applicable_steering(["src/app.py"], str(steering_dir))
        assert len(result) == 1

    def test_sorts_by_priority_descending(self, steering_dir: Path) -> None:
        (steering_dir / "low.md").write_text(
            '---\napplyTo: "**/*.py"\npriority: 1\n---\n\nLow.\n'
        )
        (steering_dir / "high.md").write_text(
            '---\napplyTo: "**/*.py"\npriority: 10\n---\n\nHigh.\n'
        )
        result = get_applicable_steering(["src/app.py"], str(steering_dir))
        assert len(result) == 2
        assert result[0]["Priority"] > result[1]["Priority"]

    def test_default_priority_is_5(self, steering_dir: Path) -> None:
        (steering_dir / "no-prio.md").write_text(
            '---\napplyTo: "**/*.py"\n---\n\nDefault priority.\n'
        )
        result = get_applicable_steering(["src/app.py"], str(steering_dir))
        assert len(result) == 1
        assert result[0]["Priority"] == 5

    def test_skips_files_without_apply_to(self, steering_dir: Path) -> None:
        (steering_dir / "no-apply.md").write_text(
            "---\npriority: 5\n---\n\nNo apply.\n"
        )
        result = get_applicable_steering(["anything.py"], str(steering_dir))
        assert len(result) == 0

    def test_skips_files_without_frontmatter(self, steering_dir: Path) -> None:
        (steering_dir / "plain.md").write_text("# No frontmatter\nJust text.\n")
        result = get_applicable_steering(["anything.py"], str(steering_dir))
        assert len(result) == 0


class TestMain:
    """Tests for main entry point."""

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        sdir = tmp_path / "steering"
        sdir.mkdir()
        (sdir / "test.md").write_text(
            '---\napplyTo: "**/*.py"\npriority: 5\n---\n\nTest.\n'
        )
        with patch("sys.argv", [
            "get_applicable_steering.py",
            "--files", "src/app.py",
            "--steering-path", str(sdir),
            "--json",
        ]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert '"Name"' in captured.out

    def test_human_output_no_matches(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        sdir = tmp_path / "steering"
        sdir.mkdir()
        with patch("sys.argv", [
            "get_applicable_steering.py",
            "--files", "src/app.py",
            "--steering-path", str(sdir),
        ]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "No applicable" in captured.out
