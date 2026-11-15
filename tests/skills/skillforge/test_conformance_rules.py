"""One passing and one failing fixture for each automated conformance rule."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.skills.skillforge.conformance_support import (
    DEFAULT_BODY,
    DESCRIPTION,
    RULES,
    make_skill,
    results,
)

AUTOMATED = [rule.id for rule in RULES if not rule.manual]


def _status(skill: Path, rule_id: str, profile: str = "spec") -> str:
    return results(skill, profile)[rule_id].status


def _problems(skill: Path, rule_id: str) -> str:
    return " | ".join(results(skill)[rule_id].problems)


def test_minimal_skill_passes_every_automated_rule(tmp_path: Path) -> None:
    found = results(make_skill(tmp_path))
    bad = {
        rid: r.status
        for rid, r in found.items()
        if r.status not in ("PASS", "NOT_APPLICABLE", "MANUAL")
    }
    assert bad == {}


@pytest.mark.parametrize("rule_id", AUTOMATED)
def test_every_automated_rule_has_a_failing_fixture(rule_id: str) -> None:
    assert rule_id in FAILING, f"add a failing fixture for {rule_id}"


def _fm(name: str = "release-notes", description: str = DESCRIPTION, extra: str = "") -> str:
    return f"name: {name}\ndescription: {description}\n{extra}"


FAILING: dict[str, dict[str, object]] = {
    "spec.skill-md.present": {"setup": "no-skill-md"},
    "spec.frontmatter.delimited": {"setup": "no-frontmatter"},
    "spec.frontmatter.mapping": {
        "frontmatter": _fm(extra="name: twice\n"),
        "expect": "duplicate key",
    },
    "spec.frontmatter.known-fields": {
        "frontmatter": _fm(extra="version: 1.0.0\n"),
        "expect": "version",
    },
    "spec.name.present": {"frontmatter": _fm(name='""'), "expect": "missing or empty"},
    "spec.name.max-length": {"name": "a" * 65, "expect": "65 characters"},
    "spec.name.charset": {"name": "release_notes", "expect": "_"},
    "spec.name.hyphen-edges": {"name": "release-notes-", "expect": "hyphen"},
    "spec.name.no-double-hyphen": {"name": "release--notes", "expect": "'--'"},
    "spec.name.matches-directory": {
        "frontmatter": _fm(name="other-name"),
        "expect": "directory name",
    },
    "spec.description.present": {
        "frontmatter": _fm(description='""'),
        "expect": "missing or empty",
    },
    "spec.description.max-length": {"frontmatter": _fm(description="x" * 1025), "expect": "1025"},
    "spec.compatibility.length": {
        "frontmatter": _fm(extra=f"compatibility: {'y' * 501}\n"),
        "expect": "501",
    },
    "spec.metadata.string-map": {
        "frontmatter": _fm(extra="metadata:\n  version: 1.0\n"),
        "expect": "float",
    },
    "spec.allowed-tools.string": {
        "frontmatter": _fm(extra="allowed-tools:\n  - Read\n"),
        "expect": "a list",
    },
    "spec.body.max-lines": {"body": "line\n" * 500, "expect": "lines"},
    "spec.body.token-budget": {"body": "word " * 5000, "expect": "tokens"},
    "spec.references.relative": {
        "body": "See [x](/etc/hosts) and [y](../up.md).\n",
        "expect": "absolute",
    },
    "spec.references.resolve": {
        "body": "See [guide](references/missing.md).\n",
        "expect": "missing.md",
    },
    "spec.references.one-level": {
        "body": "See [a](references/a.md).\n",
        "files": {"references/a.md": "Then [b](b.md).\n", "references/b.md": "# B\n"},
        "expect": "only through",
    },
    "scripts.pinned-one-off": {"body": "```bash\nuvx ruff check .\n```\n", "expect": "uvx ruff"},
    "scripts.listed-in-skill-md": {
        "files": {"scripts/run.py": 'import argparse\nif __name__ == "__main__":\n    pass\n'},
        "expect": "run.py (scripts directory)",
    },
    "scripts.no-interactive-prompts": {
        "body": "Run `run.py --help`.\n",
        "files": {
            "scripts/run.py": 'import argparse\nif __name__ == "__main__":\n    input("go? ")\n'
        },
        "expect": "run.py:3",
    },
    "scripts.help": {
        "body": "Run `run.py`.\n",
        "files": {"scripts/run.py": 'import sys\nif __name__ == "__main__":\n    sys.exit(0)\n'},
        "expect": "--help",
    },
    "scripts.exit-codes": {
        "body": "Run `run.py --help`.\n",
        "files": {"scripts/run.py": 'import argparse\nif __name__ == "__main__":\n    pass\n'},
        "expect": "run.py: no exit code documentation",
    },
    "evals.file-shape": {
        "files": {"evals/evals.json": '{"skill_name": "other", "evals": []}'},
        "expect": "skill_name",
    },
}


@pytest.mark.parametrize("rule_id", sorted(FAILING))
def test_failing_fixture_fails_its_rule(tmp_path: Path, rule_id: str) -> None:
    case = FAILING[rule_id]
    if case.get("setup") == "no-skill-md":
        skill = tmp_path / "release-notes"
        skill.mkdir()
    elif case.get("setup") == "no-frontmatter":
        skill = tmp_path / "release-notes"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# No frontmatter\n", encoding="utf-8")
    else:
        name = str(case.get("name", "release-notes"))
        frontmatter = case.get("frontmatter")
        if frontmatter is None and "name" in case:
            frontmatter = _fm(name=name)
        files = case.get("files")
        skill = make_skill(
            tmp_path,
            name,
            frontmatter=None if frontmatter is None else str(frontmatter),
            body=str(case.get("body", DEFAULT_BODY)),
            files=files if isinstance(files, dict) else None,
        )
    rule = next(r for r in RULES if r.id == rule_id)
    result = results(skill)[rule_id]
    assert result.status == ("FAIL" if rule.level == "MUST" else "WARN"), result
    if "expect" in case:
        assert str(case["expect"]) in " | ".join(result.problems)


class TestBoundaries:
    def test_name_and_description_limits_are_inclusive(self, tmp_path: Path) -> None:
        name = "a" * 64
        skill = make_skill(tmp_path, name, frontmatter=_fm(name=name, description="d" * 1024))
        assert _status(skill, "spec.name.max-length") == "PASS"
        assert _status(skill, "spec.description.max-length") == "PASS"

    def test_unicode_lowercase_name_is_allowed(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, "café-notes")
        assert _status(skill, "spec.name.charset") == "PASS"

    def test_uppercase_name_fails(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, "Release-Notes")
        assert "lowercase" in _problems(skill, "spec.name.charset")

    def test_compatibility_500_passes_and_empty_fails(self, tmp_path: Path) -> None:
        ok = make_skill(tmp_path / "a", frontmatter=_fm(extra=f"compatibility: {'y' * 500}\n"))
        empty = make_skill(tmp_path / "b", frontmatter=_fm(extra='compatibility: ""\n'))
        assert _status(ok, "spec.compatibility.length") == "PASS"
        assert "empty" in _problems(empty, "spec.compatibility.length")

    def test_absent_optional_fields_are_not_applicable(self, tmp_path: Path) -> None:
        found = results(make_skill(tmp_path))
        for rule_id in (
            "spec.compatibility.length",
            "spec.metadata.string-map",
            "spec.allowed-tools.string",
        ):
            assert found[rule_id].status == "NOT_APPLICABLE"

    def test_body_499_lines_passes(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, body="line\n" * 490)
        assert _status(skill, "spec.body.max-lines") == "PASS"

    def test_folded_description_length_counts_the_folded_text(self, tmp_path: Path) -> None:
        folded = "description: >-\n  " + "x" * 600 + "\n  " + "y" * 600 + "\n"
        skill = make_skill(tmp_path, frontmatter="name: release-notes\n" + folded)
        assert _status(skill, "spec.description.max-length") == "FAIL"
        assert "1201 characters" in _problems(skill, "spec.description.max-length")

    def test_literal_description_keeps_its_clipped_newline(self, tmp_path: Path) -> None:
        literal = "description: |\n  " + "x" * 1023 + "\n"
        skill = make_skill(tmp_path, frontmatter="name: release-notes\n" + literal)
        assert "1024" not in _problems(skill, "spec.description.max-length")
        assert _status(skill, "spec.description.max-length") == "PASS"


class TestTypedFields:
    def test_quoted_metadata_values_pass(self, tmp_path: Path) -> None:
        skill = make_skill(
            tmp_path, frontmatter=_fm(extra='metadata:\n  version: "1.0"\n  author: me\n')
        )
        assert _status(skill, "spec.metadata.string-map") == "PASS"

    def test_nested_metadata_value_warns(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(extra="metadata:\n  owner:\n    team: x\n"))
        assert "a mapping" in _problems(skill, "spec.metadata.string-map")

    def test_space_separated_allowed_tools_passes(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(extra="allowed-tools: Bash(git:*) Read\n"))
        assert _status(skill, "spec.allowed-tools.string") == "PASS"

    def test_flow_list_allowed_tools_warns(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(extra="allowed-tools: [Read, Grep]\n"))
        assert "a list" in _problems(skill, "spec.allowed-tools.string")


class TestReferences:
    def test_existing_link_resolves(self, tmp_path: Path) -> None:
        skill = make_skill(
            tmp_path, body="See [a](references/a.md#part).\n", files={"references/a.md": "# A\n"}
        )
        assert _status(skill, "spec.references.resolve") == "PASS"

    def test_links_in_code_fences_and_urls_are_ignored(self, tmp_path: Path) -> None:
        body = "```md\n[x](missing.md)\n```\nSee [site](https://example.com/a.md).\n"
        skill = make_skill(tmp_path, body=body)
        assert _status(skill, "spec.references.resolve") == "PASS"
        assert _status(skill, "spec.references.relative") == "PASS"

    def test_chain_target_also_linked_from_skill_md_passes(self, tmp_path: Path) -> None:
        skill = make_skill(
            tmp_path,
            body="See [a](references/a.md) and [b](references/b.md).\n",
            files={"references/a.md": "Then [b](b.md).\n", "references/b.md": "# B\n"},
        )
        assert _status(skill, "spec.references.one-level") == "PASS"

    def test_two_directory_link_warns(self, tmp_path: Path) -> None:
        skill = make_skill(
            tmp_path,
            body="See [d](references/deep/d.md).\n",
            files={"references/deep/d.md": "# D\n"},
        )
        assert "more than one directory" in _problems(skill, "spec.references.one-level")


class TestScripts:
    def test_helper_module_without_main_guard_is_not_an_entry_script(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, files={"scripts/helpers.py": "def f():\n    return 1\n"})
        assert _status(skill, "scripts.listed-in-skill-md") == "NOT_APPLICABLE"
        assert _status(skill, "scripts.help") == "NOT_APPLICABLE"

    def test_listed_script_with_argparse_passes(self, tmp_path: Path) -> None:
        script = (
            'import argparse\nif __name__ == "__main__":\n'
            "    argparse.ArgumentParser().parse_args()\n"
        )
        skill = make_skill(
            tmp_path, body="Run `run.py --help`.\n", files={"scripts/run.py": script}
        )
        assert _status(skill, "scripts.listed-in-skill-md") == "PASS"
        assert _status(skill, "scripts.help") == "PASS"
        assert _status(skill, "scripts.no-interactive-prompts") == "PASS"

    def test_shell_read_prompt_warns(self, tmp_path: Path) -> None:
        script = (
            '#!/bin/sh\ncase "$1" in -h|--help) echo usage;; esac\nread -r -p "Continue? " ok\n'
        )
        skill = make_skill(tmp_path, body="Run `go.sh`.\n", files={"scripts/go.sh": script})
        assert "go.sh:3" in _problems(skill, "scripts.no-interactive-prompts")

    def test_exit_codes_in_the_docstring_pass(self, tmp_path: Path) -> None:
        script = (
            '"""Run it.\n\nExit codes: 0 ok, 1 logic, 2 usage."""\n'
            'import argparse\nif __name__ == "__main__":\n    pass\n'
        )
        skill = make_skill(tmp_path, body="Run `run.py`.\n", files={"scripts/run.py": script})
        assert _status(skill, "scripts.exit-codes") == "PASS"

    def test_shell_read_loop_is_not_a_prompt(self, tmp_path: Path) -> None:
        script = '#!/bin/sh\n# --help prints usage\nwhile read -r line; do echo "$line"; done\n'
        skill = make_skill(tmp_path, body="Run `go.sh`.\n", files={"scripts/go.sh": script})
        assert _status(skill, "scripts.no-interactive-prompts") == "PASS"

    @pytest.mark.parametrize(
        "command",
        [
            "uvx ruff@0.8.0 check .",
            "npx -y eslint@9 --fix .",
            "uvx --from ruff==0.8.0 ruff check .",
            "npx @scope/tool@2 run",
            "go run golang.org/x/tools/cmd/goimports@v0.28.0 .",
        ],
    )
    def test_pinned_one_off_commands_pass(self, tmp_path: Path, command: str) -> None:
        skill = make_skill(tmp_path, body=f"```bash\n{command}\n```\n")
        assert _status(skill, "scripts.pinned-one-off") == "PASS"

    def test_unpinned_command_outside_code_is_ignored(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, body="You could run uvx ruff check . by hand.\n")
        assert _status(skill, "scripts.pinned-one-off") == "PASS"


class TestEvals:
    def test_valid_evals_file_passes(self, tmp_path: Path) -> None:
        evals = (
            '{"skill_name": "release-notes", "evals": [{"id": 1, "prompt": "Draft notes",'
            ' "expected_output": "Notes", "files": ["evals/files/in.txt"],'
            ' "assertions": ["Has a title"]}]}'
        )
        skill = make_skill(tmp_path, files={"evals/evals.json": evals, "evals/files/in.txt": "x"})
        assert _status(skill, "evals.file-shape") == "PASS"

    def test_missing_input_file_and_bad_json_warn(self, tmp_path: Path) -> None:
        evals = (
            '{"skill_name": "release-notes", "evals": [{"id": 1, "prompt": "p",'
            ' "expected_output": "o", "files": ["nope.txt"]}]}'
        )
        missing = make_skill(tmp_path / "a", files={"evals/evals.json": evals})
        broken = make_skill(tmp_path / "b", files={"evals/evals.json": "{not json"})
        assert "nope.txt does not exist" in _problems(missing, "evals.file-shape")
        assert "not valid JSON" in _problems(broken, "evals.file-shape")


class TestProfilesAndWaivers:
    def test_project_profile_reports_declared_deviation(self, tmp_path: Path) -> None:
        skill = make_skill(
            tmp_path, frontmatter=_fm(extra="version: 1.0.0\nallowed-tools:\n  - Read\n")
        )
        found = results(skill, "project")
        assert found["spec.frontmatter.known-fields"].status == "DEVIATION"
        assert found["spec.allowed-tools.string"].status == "DEVIATION"
        assert "harness fields" in found["spec.frontmatter.known-fields"].reason

    def test_waiver_wins_over_failure(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(extra="version: 1.0.0\n"))
        found = results(skill, waived={"spec.frontmatter.known-fields"})
        assert found["spec.frontmatter.known-fields"].status == "WAIVED"

    def test_project_profile_does_not_relax_undeclared_rules(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(name="other-name"))
        assert _status(skill, "spec.name.matches-directory", "project") == "FAIL"


class TestReviewedEdgeCases:
    """Cases from the PR #7376 review, each checked against YAML or the guides."""

    def test_colon_space_in_a_plain_value_is_a_parse_error(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(description="Format notes: use at release"))
        assert _status(skill, "spec.frontmatter.mapping") == "FAIL"
        assert "quote the whole value" in _problems(skill, "spec.frontmatter.mapping")

    def test_folded_paragraph_break_counts_one_newline(self, tmp_path: Path) -> None:
        folded = "description: >-\n  " + "a" * 511 + "\n\n  " + "b" * 512 + "\n"
        skill = make_skill(tmp_path, frontmatter="name: release-notes\n" + folded)
        assert _status(skill, "spec.description.max-length") == "PASS"

    def test_bare_compatibility_is_a_null_failure(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter=_fm(extra="compatibility:\n"))
        assert _status(skill, "spec.compatibility.length") == "FAIL"
        assert "got null" in _problems(skill, "spec.compatibility.length")

    def test_lowercase_skill_md_fails_the_file_name_rule(self, tmp_path: Path) -> None:
        skill = tmp_path / "release-notes"
        skill.mkdir()
        (skill / "skill.md").write_text(f"---\n{_fm()}---\n\n# Body\n", encoding="utf-8")
        assert "SKILL.md" in _problems(skill, "spec.skill-md.present")
        assert _status(skill, "spec.name.matches-directory") == "PASS"

    def test_reference_style_link_to_a_missing_file_warns(self, tmp_path: Path) -> None:
        body = "See the [guide][g].\n\n[g]: references/missing.md\n"
        skill = make_skill(tmp_path, body=body)
        assert "missing.md" in _problems(skill, "spec.references.resolve")

    def test_not_equal_main_guard_is_not_an_entry_script(self, tmp_path: Path) -> None:
        helper = 'if __name__ != "__main__":\n    VALUE = 1\n'
        skill = make_skill(tmp_path, files={"scripts/helper.py": helper})
        assert _status(skill, "scripts.listed-in-skill-md") == "NOT_APPLICABLE"

    def test_script_name_inside_a_longer_name_is_not_listed(self, tmp_path: Path) -> None:
        script = 'import argparse\nif __name__ == "__main__":\n    pass\n'
        skill = make_skill(tmp_path, body="Run `overrun.py`.\n", files={"scripts/run.py": script})
        assert "run.py (scripts directory)" in _problems(skill, "scripts.listed-in-skill-md")

    @pytest.mark.parametrize(
        ("command", "status"),
        [
            ("uvx --from=ruff==0.8.0 ruff check .", "PASS"),
            ("pipx run --spec black==24.10.0 black .", "PASS"),
            ("deno run jsr:@std/cli", "WARN"),
            ("deno run jsr:@std/cli@1.0.0", "PASS"),
            ("deno run --allow-read main.ts", "PASS"),
            ("npx ./local-tool.js", "PASS"),
            ("go run ./cmd/tool", "PASS"),
            ("npx @scope/tool", "WARN"),
        ],
    )
    def test_pinning_follows_command_syntax(
        self, tmp_path: Path, command: str, status: str
    ) -> None:
        skill = make_skill(tmp_path, body=f"```bash\n{command}\n```\n")
        assert _status(skill, "scripts.pinned-one-off") == status
