"""Tests for scripts/skill_loader.py.

Covers frontmatter parsing, protocol extraction, multi-path discovery
with precedence, and CLI subcommands (list, show, load).

See: Issue #1608 - Skill-Based Slash Commands (v0.4.0) Phase 1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.skill_loader import (  # noqa: E402
    discover_skills,
    format_skill_list,
    format_skill_show,
    load_skill,
    main,
    parse_frontmatter,
    parse_protocol,
    parse_tags,
    parse_tools_required,
)

# --- Fixtures ---


@pytest.fixture()
def skill_dir(tmp_path: Path) -> Path:
    """Create a minimal skill directory with SKILL.md."""
    skill = tmp_path / "review"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        dedent("""\
            ---
            name: code-review
            description: Architecture-first code review
            version: 1.0.0
            model: claude-sonnet-4-5
            author: test-author
            tags: [review, quality]
            user-invocable: true
            ---

            # Code Review Skill

            ## Process

            1. Clarify the goal
               - Tool: `gh pr view`
            2. Gather context
               - Tool: `git log`
               - Check file changes
            3. Review architecture

            ## Tools Required

            - `gh`
            - `git`

            ## Verification

            Check findings are actionable.
        """),
        encoding="utf-8",
    )
    return skill


@pytest.fixture()
def multi_path_setup(tmp_path: Path) -> dict[str, Path]:
    """Create two skill directories with overlapping skill names."""
    builtin = tmp_path / "builtin"
    project = tmp_path / "project"
    builtin.mkdir()
    project.mkdir()

    # Built-in review skill
    (builtin / "review").mkdir()
    (builtin / "review" / "SKILL.md").write_text(
        dedent("""\
            ---
            name: review
            description: Built-in review skill
            version: 1.0.0
            ---

            # Review (built-in)
        """),
        encoding="utf-8",
    )

    # Built-in debug skill (only in built-in)
    (builtin / "debug").mkdir()
    (builtin / "debug" / "SKILL.md").write_text(
        dedent("""\
            ---
            name: debug
            description: Debug skill
            version: 1.0.0
            ---

            # Debug
        """),
        encoding="utf-8",
    )

    # Project-level review skill (overrides built-in)
    (project / "review").mkdir()
    (project / "review" / "SKILL.md").write_text(
        dedent("""\
            ---
            name: review
            description: Project-specific review
            version: 2.0.0
            ---

            # Review (project)
        """),
        encoding="utf-8",
    )

    return {"builtin": builtin, "project": project}


# --- parse_frontmatter ---


class TestParseFrontmatter:
    def test_standard_frontmatter(self) -> None:
        text = dedent("""\
            ---
            name: test-skill
            description: A test skill
            version: 1.0.0
            ---

            # Content
        """)
        result = parse_frontmatter(text)
        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill"
        assert result["version"] == "1.0.0"

    def test_empty_text(self) -> None:
        assert parse_frontmatter("") == {}

    def test_no_frontmatter(self) -> None:
        assert parse_frontmatter("# Just a heading\n\nSome content.") == {}

    def test_unclosed_frontmatter(self) -> None:
        text = "---\nname: broken\nno closing delimiter"
        assert parse_frontmatter(text) == {}

    def test_multiword_values(self) -> None:
        text = "---\ndescription: A long description with spaces\n---\n"
        result = parse_frontmatter(text)
        assert result["description"] == "A long description with spaces"


# --- parse_protocol ---


class TestParseProtocol:
    def test_numbered_steps(self) -> None:
        text = dedent("""\
            # Skill

            ## Process

            1. First step
            2. Second step
            3. Third step

            ## Other Section
        """)
        steps = parse_protocol(text)
        assert len(steps) == 3
        assert steps[0].order == 1
        assert steps[0].description == "First step"
        assert steps[2].order == 3

    def test_steps_with_tools(self) -> None:
        text = dedent("""\
            ## Protocol

            1. Check status
               - Tool: `gh pr view`
            2. Review diff
               - Tool: `git diff`
        """)
        steps = parse_protocol(text)
        assert len(steps) == 2
        assert steps[0].tool == "gh pr view"
        assert steps[1].tool == "git diff"

    def test_steps_with_substeps(self) -> None:
        text = dedent("""\
            ## Process

            1. Gather context
               - Check file changes
               - Read PR description
               - Tool: `gh pr view`
            2. Analyze
        """)
        steps = parse_protocol(text)
        assert len(steps) == 2
        assert steps[0].substeps == ("Check file changes", "Read PR description")
        assert steps[0].tool == "gh pr view"

    def test_no_protocol_section(self) -> None:
        text = "# Skill\n\n## Triggers\n\n- trigger1"
        assert parse_protocol(text) == []

    def test_protocol_at_end_of_file(self) -> None:
        text = dedent("""\
            ## Process

            1. Only step
        """)
        steps = parse_protocol(text)
        assert len(steps) == 1
        assert steps[0].description == "Only step"


# --- parse_tags ---


class TestParseTags:
    def test_bracket_notation(self) -> None:
        assert parse_tags("[review, quality, testing]") == (
            "review",
            "quality",
            "testing",
        )

    def test_quoted_tags(self) -> None:
        assert parse_tags("['review', \"quality\"]") == ("review", "quality")

    def test_empty(self) -> None:
        assert parse_tags("") == ()
        assert parse_tags("[]") == ()

    def test_bare_values(self) -> None:
        assert parse_tags("review, quality") == ("review", "quality")


# --- parse_tools_required ---


class TestParseToolsRequired:
    def test_standard_tools_section(self) -> None:
        text = dedent("""\
            ## Tools Required

            - `gh`
            - `git`
            - `curl`

            ## Next Section
        """)
        tools = parse_tools_required(text)
        assert tools == ("gh", "git", "curl")

    def test_no_tools_section(self) -> None:
        assert parse_tools_required("# Skill\n\nNo tools.") == ()


# --- load_skill ---


class TestLoadSkill:
    def test_load_valid_skill(self, skill_dir: Path) -> None:
        skill = load_skill(skill_dir)
        assert skill.name == "code-review"
        assert skill.description == "Architecture-first code review"
        assert skill.version == "1.0.0"
        assert skill.model == "claude-sonnet-4-5"
        assert skill.author == "test-author"
        assert skill.tags == ("review", "quality")
        assert skill.user_invocable is True
        assert len(skill.protocol) == 3
        assert skill.protocol[0].tool == "gh pr view"
        assert skill.tools == ("gh", "git")

    def test_missing_skill_md(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="SKILL.md not found"):
            load_skill(empty_dir)

    def test_skill_name_fallback_to_dir_name(self, tmp_path: Path) -> None:
        skill = tmp_path / "my-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            "---\ndescription: no name field\n---\n# Skill\n",
            encoding="utf-8",
        )
        result = load_skill(skill)
        assert result.name == "my-skill"


# --- discover_skills ---


class TestDiscoverSkills:
    def test_precedence_project_over_builtin(
        self, multi_path_setup: dict[str, Path]
    ) -> None:
        # Project path listed first (higher precedence)
        skills = discover_skills(
            [multi_path_setup["project"], multi_path_setup["builtin"]]
        )
        assert "review" in skills
        assert skills["review"].description == "Project-specific review"
        assert skills["review"].version == "2.0.0"

    def test_builtin_only_skills_included(
        self, multi_path_setup: dict[str, Path]
    ) -> None:
        skills = discover_skills(
            [multi_path_setup["project"], multi_path_setup["builtin"]]
        )
        assert "debug" in skills
        assert skills["debug"].description == "Debug skill"

    def test_nonexistent_path_skipped(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does-not-exist"
        skills = discover_skills([nonexistent])
        assert skills == {}

    def test_empty_directory(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        skills = discover_skills([empty])
        assert skills == {}

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".hidden-skill"
        hidden.mkdir()
        (hidden / "SKILL.md").write_text("---\nname: hidden\n---\n", encoding="utf-8")
        skills = discover_skills([tmp_path])
        assert "hidden" not in skills

    def test_skips_dirs_without_skill_md(self, tmp_path: Path) -> None:
        no_skill = tmp_path / "no-skill"
        no_skill.mkdir()
        (no_skill / "README.md").write_text("Not a skill", encoding="utf-8")
        skills = discover_skills([tmp_path])
        assert skills == {}


# --- format_skill_list ---


class TestFormatSkillList:
    def test_json_format(self, skill_dir: Path) -> None:
        skills = discover_skills([skill_dir.parent])
        output = format_skill_list(skills, "json")
        data = json.loads(output)
        assert len(data) == 1
        assert data[0]["name"] == "code-review"
        assert data[0]["steps"] == 3
        assert data[0]["user_invocable"] is True

    def test_table_format(self, skill_dir: Path) -> None:
        skills = discover_skills([skill_dir.parent])
        output = format_skill_list(skills, "table")
        assert "code-review" in output
        assert "| Name |" in output


# --- format_skill_show ---


class TestFormatSkillShow:
    def test_show_includes_all_fields(self, skill_dir: Path) -> None:
        skill = load_skill(skill_dir)
        output = format_skill_show(skill)
        assert "# code-review" in output
        assert "Architecture-first code review" in output
        assert "1.0.0" in output
        assert "claude-sonnet-4-5" in output
        assert "test-author" in output
        assert "review, quality" in output
        assert "Protocol Steps" in output
        assert "Clarify the goal" in output
        assert "`gh`" in output


# --- CLI (main) ---


class TestCLI:
    def test_list_json(self, skill_dir: Path, capsys: pytest.CaptureFixture) -> None:
        rc = main(["list", "--search-paths", str(skill_dir.parent)])
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert len(data) == 1

    def test_list_table(self, skill_dir: Path, capsys: pytest.CaptureFixture) -> None:
        rc = main(["list", "--format", "table", "--search-paths", str(skill_dir.parent)])
        assert rc == 0
        output = capsys.readouterr().out
        assert "code-review" in output

    def test_show_markdown(
        self, skill_dir: Path, capsys: pytest.CaptureFixture
    ) -> None:
        rc = main(["show", "code-review", "--search-paths", str(skill_dir.parent)])
        assert rc == 0
        output = capsys.readouterr().out
        assert "# code-review" in output

    def test_show_json(self, skill_dir: Path, capsys: pytest.CaptureFixture) -> None:
        rc = main([
            "show",
            "code-review",
            "--format",
            "json",
            "--search-paths",
            str(skill_dir.parent),
        ])
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["name"] == "code-review"

    def test_show_not_found(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        rc = main(["show", "nonexistent", "--search-paths", str(empty)])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_load_json(self, skill_dir: Path, capsys: pytest.CaptureFixture) -> None:
        rc = main(["load", "code-review", "--search-paths", str(skill_dir.parent)])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["name"] == "code-review"
        assert len(data["protocol"]) == 3

    def test_load_not_found(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        rc = main(["load", "nonexistent", "--search-paths", str(empty)])
        assert rc == 1
