"""Validator alignment with the agentskills.io specification.

Spec: https://agentskills.io/specification. Covers the compatibility field,
the hard 1024-character description limit, blank required fields, the name
to directory match, the space-separated allowed-tools form, digit-first
names, and the one-level-deep file reference rule.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_DIR = _PROJECT_ROOT / ".claude" / "skills" / "skillforge" / "scripts"


def _drop_script_modules(saved: set[str]) -> None:
    """Drop only modules this test loaded from the skillforge script dir.

    Third-party modules such as `yaml` stay cached. Evicting them would give
    later importers a second module object and split class identity.
    """
    script_dir = _SCRIPT_DIR.resolve()
    for added in set(sys.modules) - saved:
        origin = getattr(sys.modules[added], "__file__", None)
        if origin and Path(origin).resolve().parent == script_dir:
            del sys.modules[added]


def _load(name: str, filename: str):
    # Load with the script dir on sys.path, then restore sys.path and drop the
    # sibling helper modules so mirror-tree tests import their own copies.
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    sys.path.insert(0, str(_SCRIPT_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, _SCRIPT_DIR / filename)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        _drop_script_modules(saved_modules)
    return module


validate_skill_mod = _load("skillforge_validate_skill_spec", "validate-skill.py")
quick = _load("skillforge_quick_validate_spec", "quick_validate.py")
constants = _load("skillforge_constants_spec", "_constants.py")


@pytest.fixture(autouse=True)
def _script_dir_on_path():
    """Let lazy `from _constants import` resolve to this tree, then clean up.

    The validators import `_constants` inside functions. Without the script dir
    on sys.path they fall back to inline copies, which would leave the shared
    constants untested. Helper modules added here are dropped afterward.
    """
    saved_path = list(sys.path)
    saved_modules = set(sys.modules)
    sys.path.insert(0, str(_SCRIPT_DIR))
    try:
        yield
    finally:
        sys.path[:] = saved_path
        _drop_script_modules(saved_modules)


def test_shared_constants_are_used() -> None:
    """Guard against silently testing only the inline fallback copies."""
    import _constants

    assert Path(_constants.__file__).resolve().parent == _SCRIPT_DIR.resolve()
    assert "compatibility" in _constants.ALLOWED_PROPERTIES
    assert _constants.COMPATIBILITY_MAX_LENGTH == 500


DESCRIPTION = "Format release notes from merged pull requests. Use when drafting a release."


def _write(root: Path, name: str, extra: str = "", body: str = "# Title\n", *, desc=None) -> Path:
    skill = root / name
    skill.mkdir(parents=True, exist_ok=True)
    description = DESCRIPTION if desc is None else desc
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n{body}",
        encoding="utf-8",
    )
    return skill


def _full(skill: Path, root: Path):
    validator = validate_skill_mod.SkillValidator(str(skill), root=str(root))
    validator.validate()
    return validator


def _has(messages: list[str], fragment: str) -> bool:
    return any(fragment in message for message in messages)


class TestCompatibility:
    def test_valid_compatibility_accepted_by_both(self, tmp_path: Path) -> None:
        extra = "compatibility: Requires git and network access to api.github.com\n"
        skill = _write(tmp_path, "rel-notes", extra)
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert ok, message
        validator = _full(skill, tmp_path)
        assert not _has(validator.errors, "Unexpected"), validator.errors
        assert not _has(validator.errors, "compatibility"), validator.errors

    def test_empty_compatibility_rejected(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", 'compatibility: "  "\n')
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "Compatibility must not be empty" in message
        assert _has(_full(skill, tmp_path).errors, "compatibility must not be empty")

    def test_500_chars_passes_501_fails(self, tmp_path: Path) -> None:
        at_limit = _write(tmp_path / "a", "rel-notes", f"compatibility: {'x' * 500}\n")
        over = _write(tmp_path / "b", "rel-notes", f"compatibility: {'x' * 501}\n")
        assert quick.validate_skill(at_limit, root=str(tmp_path))[0]
        ok, message = quick.validate_skill(over, root=str(tmp_path))
        assert not ok
        assert "Compatibility is too long (501" in message
        assert not _has(_full(at_limit, tmp_path).errors, "compatibility too long")
        assert _has(_full(over, tmp_path).errors, "compatibility too long (501")

    def test_non_string_compatibility_rejected(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", "compatibility:\n  - git\n")
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "Compatibility must be a string" in message
        assert _has(_full(skill, tmp_path).errors, "compatibility must be a string")


class TestDescriptionLimit:
    def test_1024_passes_both(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", desc="a " * 511 + "ab")
        assert quick.validate_skill(skill, root=str(tmp_path))[0]
        assert not _has(_full(skill, tmp_path).errors, "Description too long")

    def test_1025_is_an_error_in_both(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", desc="a " * 512 + "a")
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "Description is too long (1025" in message
        validator = _full(skill, tmp_path)
        assert _has(validator.errors, "Description too long (1025")
        assert not _has(validator.warnings, "Description too long")


class TestQuickValidateRequiredFields:
    def test_blank_name_rejected(self, tmp_path: Path) -> None:
        skill = tmp_path / "rel-notes"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            f'---\nname: "  "\ndescription: {DESCRIPTION}\n---\n', encoding="utf-8"
        )
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "Name must not be empty" in message

    def test_blank_description_rejected(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", desc='"   "')
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "Description must not be empty" in message

    def test_name_must_match_directory(self, tmp_path: Path) -> None:
        skill = tmp_path / "other-dir"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            f"---\nname: rel-notes\ndescription: {DESCRIPTION}\n---\n", encoding="utf-8"
        )
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "must match its directory name 'other-dir'" in message


class TestNameRegex:
    @pytest.mark.parametrize("name", ["3d-print", "a", "7", "pdf-processing", "a1-b2"])
    def test_valid_names(self, name: str) -> None:
        import re

        assert re.match(constants.NAME_REGEX, name)

    @pytest.mark.parametrize("name", ["-x", "x-", "-", "PDF", "a_b", ""])
    def test_invalid_names(self, name: str) -> None:
        import re

        assert not re.match(constants.NAME_REGEX, name)

    def test_digit_first_skill_passes_quick_validate(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "3d-print")
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert ok, message

    def test_consecutive_hyphens_rejected(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "a--b")
        ok, message = quick.validate_skill(skill, root=str(tmp_path))
        assert not ok
        assert "consecutive hyphens" in message


class TestAllowedTools:
    def test_space_separated_spec_form(self) -> None:
        tokens = validate_skill_mod.split_allowed_tools("Bash(git:*) Bash(jq:*) Read")
        assert tokens == ["Bash(git:*)", "Bash(jq:*)", "Read"]

    def test_whitespace_inside_parentheses_kept(self) -> None:
        tokens = validate_skill_mod.split_allowed_tools("Bash(git log:*) Read")
        assert tokens == ["Bash(git log:*)", "Read"]

    def test_comma_separated_still_supported(self) -> None:
        tokens = validate_skill_mod.split_allowed_tools("Read, Grep,Glob")
        assert tokens == ["Read", "Grep", "Glob"]

    def test_empty_string_yields_no_tokens(self) -> None:
        assert validate_skill_mod.split_allowed_tools("   ") == []

    def test_scoped_tools_not_reported_unknown(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", "allowed-tools: Bash(git:*) Read\n")
        validator = _full(skill, tmp_path)
        assert not _has(validator.warnings + validator.errors, "Bash(git:*)")


class TestReferenceDepth:
    def test_one_level_link_is_clean(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", body="See [guide](references/guide.md).\n")
        validator = _full(skill, tmp_path)
        assert not _has(validator.warnings, "nested more than one level")
        assert not _has(validator.warnings, "escapes the skill root")

    def test_nested_link_warns(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", body="See [deep](references/a/b.md).\n")
        validator = _full(skill, tmp_path)
        assert _has(validator.warnings, "nested more than one level deep: references/a/b.md")
        assert not _has(validator.errors, "references/a/b.md")

    def test_parent_escape_warns(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", body="See [x](../other/SKILL.md).\n")
        validator = _full(skill, tmp_path)
        assert _has(validator.warnings, "escapes the skill root: ../other/SKILL.md")

    def test_links_in_code_fences_and_urls_ignored(self, tmp_path: Path) -> None:
        body = (
            "```markdown\n[deep](references/a/b.md)\n```\n"
            "See [site](https://agentskills.io/a/b/c) and [top](#title).\n"
        )
        skill = _write(tmp_path, "rel-notes", body=body)
        validator = _full(skill, tmp_path)
        assert not _has(validator.warnings, "nested more than one level")


class TestBodyTokenBudget:
    def _budget_warnings(self, tmp_path: Path, body_chars: int) -> list[str]:
        body = "# Title\n" + "x" * (body_chars - len("# Title\n"))
        skill = _write(tmp_path, "rel-notes", body=body)
        validator = _full(skill, tmp_path)
        return [w for w in validator.warnings if "tokens (characters" in w]

    def test_body_at_budget_has_no_warning(self, tmp_path: Path) -> None:
        assert self._budget_warnings(tmp_path, 20_000) == []

    def test_body_over_budget_warns(self, tmp_path: Path) -> None:
        warnings = self._budget_warnings(tmp_path, 20_004)
        assert len(warnings) == 1
        assert "about 5001 tokens" in warnings[0]

    def test_budget_is_a_warning_not_an_error(self, tmp_path: Path) -> None:
        skill = _write(tmp_path, "rel-notes", body="x" * 40_000)
        validator = _full(skill, tmp_path)
        assert not _has(validator.errors, "tokens (characters")


class TestFallbackParser:
    """The stdlib fallback runs when PyYAML is absent; it must honor quoting."""

    def test_double_quoted_name_is_unquoted(self) -> None:
        parsed = quick._parse_frontmatter_fallback('name: "skill-doctor"\ndescription: x')
        assert parsed["name"] == "skill-doctor"

    def test_single_quoted_value_with_colon(self) -> None:
        parsed = quick._parse_frontmatter_fallback("description: 'Use when: it''s needed'")
        assert parsed["description"] == "Use when: it's needed"

    def test_escaped_double_quote_is_restored(self) -> None:
        parsed = quick._parse_frontmatter_fallback('description: "say \\"hi\\""')
        assert parsed["description"] == 'say "hi"'

    def test_unmatched_quote_is_kept(self) -> None:
        parsed = quick._parse_frontmatter_fallback('description: "half')
        assert parsed["description"] == '"half'

    def test_top_level_comment_is_not_a_key(self) -> None:
        parsed = quick._parse_frontmatter_fallback("# note: not a key\nname: a")
        assert "# note" not in parsed
        assert parsed["name"] == "a"

    def test_full_validator_fallback_matches(self, tmp_path: Path) -> None:
        skill = tmp_path / "rel-notes"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\n---\n", encoding="utf-8")
        validator = validate_skill_mod.SkillValidator(str(skill), root=str(tmp_path))
        validator._parse_frontmatter_fallback('# c: x\nname: "rel-notes"')
        assert validator.frontmatter == {"name": "rel-notes"}
