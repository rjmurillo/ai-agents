"""skill_frontmatter.py follows the agentskills.io specification for the fields it defines.

The agreement test runs one fixture set through this validator and through
skillforge's conformance suite, the repository's other reader of the spec, and
fails when their MUST verdicts differ.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts.validation.skill_frontmatter import (
    split_allowed_tools,
    validate_allowed_tools,
    validate_compatibility,
    validate_description,
    validate_license,
    validate_skill_file,
)

ROOT = Path(__file__).resolve().parents[1]
SKILLFORGE_SCRIPTS = ROOT / ".claude" / "skills" / "skillforge" / "scripts"


class TestAllowedTools:
    def test_space_separated_string_is_the_spec_form(self) -> None:
        assert validate_allowed_tools("Read Grep Glob") == []

    def test_argument_with_spaces_stays_one_tool(self) -> None:
        assert split_allowed_tools("Bash(git status:*) Read") == ["Bash(git status:*)", "Read"]
        assert validate_allowed_tools("Bash(mkdir:-p .project-toolkit/scratch) Read") == []

    def test_comma_and_list_forms_are_accepted(self) -> None:
        assert validate_allowed_tools("Read, Grep") == []
        assert validate_allowed_tools(["Read", "Bash(git:*)"]) == []

    def test_mcp_tool_names_are_accepted(self) -> None:
        assert validate_allowed_tools("mcp__github__pull_request_read github/issue_read") == []

    def test_retired_server_tool_names_are_rejected(self) -> None:
        errors = validate_allowed_tools("mcp__forgetful__search forgetful/search")
        assert errors and "mcp__forgetful__search" in errors[0]

    def test_unknown_bare_tool_is_rejected(self) -> None:
        assert validate_allowed_tools("Read Teleport") == [
            "Unknown tools in allowed-tools: Teleport"
        ]

    def test_non_string_non_list_is_rejected(self) -> None:
        assert validate_allowed_tools({"Read": True}) != []


class TestOptionalFields:
    @pytest.mark.parametrize(
        ("value", "ok"),
        [("Requires git", True), ("y" * 500, True), ("y" * 501, False), ("", False), (None, False)],
    )
    def test_compatibility(self, value: object, ok: bool) -> None:
        assert (validate_compatibility(value) == []) is ok

    def test_license_must_be_a_string(self) -> None:
        assert validate_license("MIT") == []
        assert validate_license(["MIT"]) != []

    def test_description_must_be_a_string(self) -> None:
        assert validate_description(True) == ["description must be a string, got bool"]


class TestTypedValues:
    def test_quoted_name_is_read_as_yaml(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "q-skill" / "SKILL.md"
        skill_file.parent.mkdir()
        skill_file.write_text(
            '---\nname: "q-skill"\ndescription: "Quoted: fine"\n---\n', encoding="utf-8"
        )

        result = validate_skill_file(skill_file)

        assert result.passed, result.errors

    def test_folded_description_counts_the_yaml_value(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "long-skill" / "SKILL.md"
        skill_file.parent.mkdir()
        body = "description: >-\n  " + "x" * 600 + "\n  " + "y" * 600 + "\n"
        skill_file.write_text(f"---\nname: long-skill\n{body}---\n", encoding="utf-8")

        result = validate_skill_file(skill_file)

        assert any("found 1201" in e for e in result.errors)


def _load_conformance() -> ModuleType:
    saved_path, saved = list(sys.path), set(sys.modules)
    sys.path.insert(0, str(SKILLFORGE_SCRIPTS))
    try:
        name = "conformance_for_frontmatter_agreement"
        spec = importlib.util.spec_from_file_location(name, SKILLFORGE_SCRIPTS / "conformance.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        for added in set(sys.modules) - saved:
            origin = getattr(sys.modules[added], "__file__", None)
            if origin and Path(origin).resolve().parent == SKILLFORGE_SCRIPTS.resolve():
                del sys.modules[added]
    return module


SHARED_RULES = (
    "spec.name.present",
    "spec.name.max-length",
    "spec.name.charset",
    "spec.name.hyphen-edges",
    "spec.name.no-double-hyphen",
    "spec.name.matches-directory",
    "spec.description.present",
    "spec.description.max-length",
    "spec.compatibility.length",
)

FIXTURES = {
    "ok": "name: ok\ndescription: Format notes. Use when releasing.\n",
    "edge-": "name: edge-\ndescription: d e f\n",
    "dbl--hy": "name: dbl--hy\ndescription: d e f\n",
    "mismatch": "name: other\ndescription: d e f\n",
    "upper": "name: Upper\ndescription: d e f\n",
    "long-desc": f"name: long-desc\ndescription: {'x' * 1025}\n",
    "max-desc": f"name: max-desc\ndescription: {'x' * 1024}\n",
    "no-desc": "name: no-desc\n",
    "compat-long": f"name: compat-long\ndescription: d e f\ncompatibility: {'y' * 501}\n",
    "compat-empty": 'name: compat-empty\ndescription: d e f\ncompatibility: ""\n',
    "compat-null": "name: compat-null\ndescription: d e f\ncompatibility:\n",
    "quoted": 'name: "quoted"\ndescription: "Use when: quoting"\n',
}


@pytest.mark.parametrize("directory", sorted(FIXTURES))
def test_must_verdicts_agree_with_the_conformance_suite(tmp_path: Path, directory: str) -> None:
    conformance = _load_conformance()
    skill = tmp_path / directory
    skill.mkdir()
    (skill / "SKILL.md").write_text(f"---\n{FIXTURES[directory]}---\n\n# Body\n", encoding="utf-8")

    frontmatter_ok = validate_skill_file(skill / "SKILL.md").passed
    results, _notes = conformance.evaluate(skill, "spec", set())
    conformance_ok = not any(r.rule.id in SHARED_RULES and r.status == "FAIL" for r in results)

    assert frontmatter_ok is conformance_ok
