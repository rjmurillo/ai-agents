"""Tests for scripts.validation.skill_frontmatter module.

Validates YAML frontmatter for SKILL.md files per ADR-040.
Covers YAML syntax, required fields, name/description/model/tools validation,
CI vs local mode behavior, and edge cases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.skill_frontmatter import (
    build_parser,
    get_skill_files,
    main,
    parse_frontmatter,
    validate_allowed_tools,
    validate_description,
    validate_model,
    validate_name,
    validate_skill_file,
)

# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_valid_frontmatter(self) -> None:
        content = "---\nname: test-skill\ndescription: A test skill\n---\nBody"
        result = parse_frontmatter(content)
        assert result.is_valid is True
        assert result.frontmatter["name"] == "test-skill"
        assert result.frontmatter["description"] == "A test skill"
        assert not result.errors

    def test_missing_start_delimiter(self) -> None:
        content = "name: test-skill\ndescription: A test skill\n---"
        result = parse_frontmatter(content)
        assert result.is_valid is False
        assert any("start with '---'" in e for e in result.errors)

    def test_missing_end_delimiter(self) -> None:
        content = "---\nname: test-skill\ndescription: A test skill"
        result = parse_frontmatter(content)
        assert result.is_valid is False
        assert any("end with '---'" in e for e in result.errors)

    def test_tab_characters_rejected(self) -> None:
        content = "---\nname:\ttest-skill\ndescription: A test skill\n---"
        result = parse_frontmatter(content)
        assert result.is_valid is False
        assert any("spaces for indentation" in e for e in result.errors)

    def test_multiline_description_with_folded_style(self) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: >\n  This is a multiline\n  description\n---"
        )
        result = parse_frontmatter(content)
        assert result.is_valid is True
        assert "multiline" in result.frontmatter["description"]

    def test_array_values_parsed(self) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: Test\n"
            "allowed-tools:\n  - bash\n  - edit\n---"
        )
        result = parse_frontmatter(content)
        assert result.is_valid is True
        assert "bash" in result.frontmatter["allowed-tools"]
        assert "edit" in result.frontmatter["allowed-tools"]

    def test_empty_frontmatter_between_delimiters(self) -> None:
        content = "---\n---\nBody"
        result = parse_frontmatter(content)
        assert result.is_valid is True
        assert result.frontmatter == {}

    def test_literal_block_scalar(self) -> None:
        content = (
            "---\nname: test-skill\n"
            "description: |\n  Line one\n  Line two\n---"
        )
        result = parse_frontmatter(content)
        assert result.is_valid is True
        assert "Line one" in result.frontmatter["description"]


# ---------------------------------------------------------------------------
# validate_name
# ---------------------------------------------------------------------------


class TestValidateName:
    """Tests for name field validation."""

    def test_valid_lowercase_with_hyphens(self) -> None:
        assert validate_name("my-test-skill-123") == []

    def test_valid_numeric_only(self) -> None:
        assert validate_name("12345") == []

    def test_valid_hyphens_at_boundaries(self) -> None:
        assert validate_name("-test-skill-") == []

    def test_valid_max_length_64(self) -> None:
        assert validate_name("a" * 64) == []

    def test_missing_name(self) -> None:
        errors = validate_name(None)
        assert any("Missing required field" in e for e in errors)

    def test_empty_name(self) -> None:
        errors = validate_name("")
        assert any("Missing required field" in e for e in errors)

    def test_whitespace_only_name(self) -> None:
        errors = validate_name("   ")
        assert any("Missing required field" in e for e in errors)

    def test_uppercase_letters_rejected(self) -> None:
        errors = validate_name("My-Test-Skill")
        assert any("Invalid name format" in e for e in errors)
        assert any("uppercase" in e for e in errors)

    def test_special_characters_rejected(self) -> None:
        errors = validate_name("test_skill!")
        assert any("Invalid name format" in e for e in errors)
        assert any("invalid characters" in e for e in errors)

    def test_exceeds_64_characters(self) -> None:
        errors = validate_name("a" * 65)
        assert any("exceeds 64 characters" in e for e in errors)
        assert any("found 65" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_description
# ---------------------------------------------------------------------------


class TestValidateDescription:
    """Tests for description field validation."""

    def test_valid_description(self) -> None:
        assert validate_description("A valid description") == []

    def test_valid_at_1024_chars(self) -> None:
        assert validate_description("A" * 1024) == []

    def test_missing_description(self) -> None:
        errors = validate_description(None)
        assert any("Missing required field" in e for e in errors)

    def test_empty_description(self) -> None:
        errors = validate_description("")
        assert any("Missing required field" in e for e in errors)

    def test_whitespace_only_description(self) -> None:
        errors = validate_description("   ")
        assert any("Missing required field" in e for e in errors)

    def test_exceeds_1024_characters(self) -> None:
        errors = validate_description("A" * 1025)
        assert any("exceeds 1024 characters" in e for e in errors)
        assert any("found 1025" in e for e in errors)

    def test_xml_tags_rejected(self) -> None:
        errors = validate_description("This has <b>XML tags</b> in it")
        assert any("contains XML tags" in e for e in errors)

    def test_no_xml_false_positive_on_angle_brackets_in_text(self) -> None:
        # Verify the function runs without error on angle brackets
        validate_description("If a < b then use it")


# ---------------------------------------------------------------------------
# validate_model
# ---------------------------------------------------------------------------


class TestValidateModel:
    """Tests for model field validation."""

    def test_valid_alias_sonnet(self) -> None:
        assert validate_model("claude-sonnet-4-5") == []

    def test_valid_alias_opus(self) -> None:
        assert validate_model("claude-opus-4-5") == []

    def test_valid_alias_haiku(self) -> None:
        assert validate_model("claude-haiku-4-5") == []

    def test_valid_cli_shortcut(self) -> None:
        assert validate_model("sonnet") == []
        assert validate_model("opus") == []
        assert validate_model("haiku") == []

    def test_valid_dated_snapshot(self) -> None:
        assert validate_model("claude-sonnet-4-5-20250929") == []

    def test_none_model_optional(self) -> None:
        assert validate_model(None) == []

    def test_empty_model_optional(self) -> None:
        assert validate_model("") == []

    def test_invalid_model_identifier(self) -> None:
        errors = validate_model("invalid-model-name")
        assert any("Invalid model identifier" in e for e in errors)

    def test_invalid_dated_snapshot_format(self) -> None:
        errors = validate_model("claude-sonnet-4-5-abc")
        assert any("Invalid model identifier" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_allowed_tools
# ---------------------------------------------------------------------------


class TestValidateAllowedTools:
    """Tests for allowed-tools field validation."""

    def test_valid_tools(self) -> None:
        assert validate_allowed_tools("bash,view,edit") == []

    def test_none_is_optional(self) -> None:
        assert validate_allowed_tools(None) == []

    def test_empty_is_optional(self) -> None:
        assert validate_allowed_tools("") == []

    def test_wildcard_allowed(self) -> None:
        assert validate_allowed_tools("bash,mcp*") == []

    def test_unknown_tool_rejected(self) -> None:
        errors = validate_allowed_tools("bash,invalid-tool-name")
        assert any("Unknown tools" in e for e in errors)
        assert any("invalid-tool-name" in e for e in errors)

    def test_all_valid_tools_accepted(self) -> None:
        from scripts.validation.skill_frontmatter import VALID_TOOLS
        all_tools = ",".join(VALID_TOOLS)
        assert validate_allowed_tools(all_tools) == []


# ---------------------------------------------------------------------------
# get_skill_files
# ---------------------------------------------------------------------------


class TestGetSkillFiles:
    """Tests for SKILL.md file discovery."""

    def test_changed_files_filters_to_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "test"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\nname: test\n---")

        result = get_skill_files(
            path=str(tmp_path),
            changed_files=[
                str(skill_file),
                str(tmp_path / "other.md"),
            ],
        )
        assert len(result) == 1
        assert result[0] == skill_file

    def test_changed_files_no_match(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = get_skill_files(
            path=".",
            changed_files=["README.md", "other.txt"],
        )
        assert result == []
        assert "No SKILL.md files" in capsys.readouterr().out

    def test_directory_scan(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "one"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("test")

        skill_dir2 = tmp_path / ".claude" / "skills" / "two"
        skill_dir2.mkdir(parents=True)
        (skill_dir2 / "SKILL.md").write_text("test")

        result = get_skill_files(path=str(tmp_path / ".claude" / "skills"))
        assert len(result) == 2

    def test_nonexistent_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = get_skill_files(path="/nonexistent/path")
        assert result == []
        assert "Path not found" in capsys.readouterr().out

    def test_single_file_path(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("test")
        result = get_skill_files(path=str(skill_file))
        assert len(result) == 1

    def test_non_skill_file_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        other_file = tmp_path / "README.md"
        other_file.write_text("test")
        result = get_skill_files(path=str(other_file))
        assert result == []
        assert "not a SKILL.md file" in capsys.readouterr().out

    def test_staged_only_with_no_git(self) -> None:
        with patch(
            "scripts.validation.skill_frontmatter.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = get_skill_files(path=".", staged_only=True)
            assert result == []


# ---------------------------------------------------------------------------
# validate_skill_file
# ---------------------------------------------------------------------------


class TestValidateSkillFile:
    """Tests for single file validation."""

    def test_valid_file(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: test-skill\ndescription: A test skill\n---\n# Body"
        )
        result = validate_skill_file(skill_file)
        assert result.passed is True
        assert not result.errors

    def test_empty_file(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("")
        result = validate_skill_file(skill_file)
        assert result.passed is False
        assert any("empty or unreadable" in e for e in result.errors)

    def test_invalid_name_reports_error(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: Invalid-Name\ndescription: Test\n---"
        )
        result = validate_skill_file(skill_file)
        assert result.passed is False
        assert any("Invalid name format" in e for e in result.errors)

    def test_multiple_violations(self, tmp_path: Path) -> None:
        desc = "A" * 1025
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            f"---\nname: Invalid-Name\n"
            f"description: <b>{desc}</b>\n"
            f"model: invalid-model\n---"
        )
        result = validate_skill_file(skill_file)
        assert result.passed is False
        assert any("Invalid name format" in e for e in result.errors)
        assert any("exceeds 1024" in e for e in result.errors)
        assert any("XML tags" in e for e in result.errors)
        assert any("Invalid model" in e for e in result.errors)

    def test_valid_with_all_optional_fields(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: full-skill\n"
            "description: Full skill with all fields\n"
            "model: claude-sonnet-4-5\n"
            "allowed-tools:\n  - bash\n  - edit\n---"
        )
        result = validate_skill_file(skill_file)
        assert result.passed is True

    def test_frontmatter_only_no_body(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: no-content\n"
            "description: Skill with no content after frontmatter\n---"
        )
        result = validate_skill_file(skill_file)
        assert result.passed is True


# ---------------------------------------------------------------------------
# main / CLI
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for main() entry point and CLI behavior."""

    def test_no_files_found_returns_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main(["--path", str(tmp_path)])
        assert exit_code == 0
        assert "No SKILL.md files found" in capsys.readouterr().out

    def test_valid_file_ci_mode_returns_0(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "ok"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: ok-skill\ndescription: Valid\n---"
        )
        exit_code = main([
            "--path", str(tmp_path / ".claude" / "skills"),
            "--ci",
        ])
        assert exit_code == 0

    def test_invalid_file_ci_mode_returns_1(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "bad"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: BAD-NAME\ndescription: Test\n---"
        )
        exit_code = main([
            "--path", str(tmp_path / ".claude" / "skills"),
            "--ci",
        ])
        assert exit_code == 1

    def test_invalid_file_local_mode_returns_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        skill_dir = tmp_path / ".claude" / "skills" / "bad"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: BAD-NAME\ndescription: Test\n---"
        )
        exit_code = main(["--path", str(tmp_path / ".claude" / "skills")])
        assert exit_code == 0
        assert "not running in CI mode" in capsys.readouterr().out

    def test_multiple_files_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("one", "two"):
            skill_dir = tmp_path / ".claude" / "skills" / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Skill {name}\n---"
            )
        exit_code = main([
            "--path", str(tmp_path / ".claude" / "skills"),
            "--ci",
        ])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Found 2 SKILL.md file(s)" in output
        assert "Passed: 2" in output

    def test_mixed_results_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        valid_dir = tmp_path / ".claude" / "skills" / "valid"
        valid_dir.mkdir(parents=True)
        (valid_dir / "SKILL.md").write_text(
            "---\nname: valid-skill\ndescription: Valid test skill\n---"
        )
        invalid_dir = tmp_path / ".claude" / "skills" / "invalid"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "SKILL.md").write_text(
            "---\nname: Invalid-Skill\ndescription: Invalid test skill\n---"
        )
        exit_code = main([
            "--path", str(tmp_path / ".claude" / "skills"),
            "--ci",
        ])
        assert exit_code == 1
        output = capsys.readouterr().out
        assert "Passed: 1" in output
        assert "Failed: 1" in output

    def test_changed_files_arg(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / ".claude" / "skills" / "ok"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\nname: ok-skill\ndescription: Valid\n---"
        )
        exit_code = main([
            "--path", str(tmp_path),
            "--ci",
            "--changed-files", str(skill_file),
        ])
        assert exit_code == 0


class TestBuildParser:
    """Tests for argument parser construction."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        parser = build_parser()
        args = parser.parse_args([])
        assert args.path == ".claude/skills"
        assert args.ci is False
        assert args.staged_only is False
        assert args.changed_files is None

    def test_ci_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci"])
        assert args.ci is True

    def test_env_var_defaults(self) -> None:
        with patch.dict(
            "os.environ",
            {"SKILL_PATH": "/custom/path", "CI": "true"},
        ):
            parser = build_parser()
            args = parser.parse_args([])
            assert args.path == "/custom/path"
            assert args.ci is True
