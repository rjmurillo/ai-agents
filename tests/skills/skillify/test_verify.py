"""Read-back verification of a written SKILL.md."""

from __future__ import annotations

import pytest
import skillify
import skillify_verify
from skill_fixtures import GOOD_SKILL, make_skill

TRIGGER = "ingest a meeting transcript"


def verify(path, trigger=TRIGGER, external=False):
    return skillify.verify_skill(skillify.resolve_skill_file(path), trigger, external)


def failed(result):
    return set(result["failures"])


def test_good_skill_passes_and_reports_name_and_trigger(skills_root):
    skill = make_skill(skills_root, "meeting-ingest")
    result = verify(skill)
    assert result["status"] == "PASS"
    assert result["name"] == "meeting-ingest"
    assert result["trigger"] == TRIGGER
    assert result["failures"] == []


def test_accepts_directory_path(skills_root):
    make_skill(skills_root, "meeting-ingest")
    assert verify(skills_root / "meeting-ingest")["status"] == "PASS"


@pytest.mark.parametrize("name", ["Meeting_Ingest", "meeting--ingest", "-lead", "x" * 65, ""])
def test_rejects_bad_names(skills_root, name):
    body = GOOD_SKILL.format(name=name, description=f"{TRIGGER}.", trigger=TRIGGER)
    skill = make_skill(skills_root, "dir-name", body=body)
    assert "name_kebab_case" in failed(verify(skill))


def test_rejects_name_that_differs_from_directory(skills_root):
    body = GOOD_SKILL.format(name="other-name", description=TRIGGER, trigger=TRIGGER)
    skill = make_skill(skills_root, "dir-name", body=body)
    assert failed(verify(skill)) == {"name_matches_directory"}


def test_rejects_empty_description(skills_root):
    body = GOOD_SKILL.format(name="a-skill", description="", trigger=TRIGGER)
    skill = make_skill(skills_root, "a-skill", body=body)
    assert "description_leads_with_trigger" in failed(verify(skill))


def test_rejects_trigger_buried_after_lead_window(skills_root):
    description = "x" * 220 + f" {TRIGGER}"
    skill = make_skill(skills_root, "a-skill", description=description)
    assert failed(verify(skill)) == {"description_leads_with_trigger"}


def test_trigger_match_ignores_case_and_whitespace(skills_root):
    skill = make_skill(skills_root, "a-skill", description="Please   INGEST a  Meeting transcript")
    assert verify(skill)["status"] == "PASS"


def test_blank_trigger_argument_fails(skills_root):
    skill = make_skill(skills_root, "a-skill")
    assert "description_leads_with_trigger" in failed(verify(skill, trigger="  "))


@pytest.mark.parametrize("section", list(skillify_verify.REQUIRED_SECTIONS))
def test_each_missing_required_section_fails(skills_root, section):
    heading = "Anti-patterns" if section == "anti-patterns" else section.capitalize()
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace(f"## {heading}\n", f"## Renamed {section}\n")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert f"section_{section}" in failed(verify(skill))


def test_heading_variants_are_accepted(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("## Anti-patterns", "### Anti Patterns:")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert "section_anti-patterns" not in failed(verify(skill))


def test_anti_patterns_needs_two_items(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("- Publishing without approval.\n", "")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify(skill)) == {"items_anti-patterns"}


def test_pitfalls_table_counts_data_rows_only(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("| CRLF line endings | Read as text |\n", "")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify(skill)) == {"items_pitfalls"}


def test_numbered_items_count(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace(
        "- Guessing the destination.\n- Publishing without approval.\n", "1. one\n2) two\n"
    )
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify(skill)["status"] == "PASS"


def test_bullets_inside_code_fence_do_not_count(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace(
        "- Guessing the destination.\n- Publishing without approval.\n",
        "```text\n- one\n- two\n# not a heading\n```\n",
    )
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify(skill)) == {"items_anti-patterns"}


def test_subsection_items_count_toward_parent(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace(
        "- Guessing the destination.\n- Publishing without approval.\n",
        "### Paths\n\n- one\n- two\n",
    )
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify(skill)["status"] == "PASS"


def test_external_actions_require_approval_gate(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("Ask for approval before publishing it.", "Publish it.")
    text = text.replace("Publishing without approval.", "Publishing blindly.")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify(skill, external=False)["status"] == "PASS"
    assert failed(verify(skill, external=True)) == {"approval_gate_present"}


def test_external_actions_pass_when_gate_present(skills_root):
    skill = make_skill(skills_root, "a-skill", trigger=TRIGGER)
    assert verify(skill, external=True)["status"] == "PASS"


@pytest.mark.parametrize("tool", list(skillify_verify.SOURCE_ONLY_TOOLS))
def test_source_only_tool_names_fail(skills_root, tool):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    skill = make_skill(skills_root, "a-skill", body=text + f"\nCall {tool}().\n")
    assert failed(verify(skill)) == {"no_source_only_tool_names"}


def test_missing_frontmatter_fails_name_and_description(skills_root):
    skill = make_skill(skills_root, "a-skill", body="# Just a body\n")
    result = verify(skill)
    assert result["status"] == "FAIL"
    assert {"name_kebab_case", "description_leads_with_trigger"} <= failed(result)


def test_unterminated_frontmatter_is_treated_as_missing(skills_root):
    skill = make_skill(skills_root, "a-skill", body="---\nname: a-skill\n# never closed\n")
    assert "name_kebab_case" in failed(verify(skill))


def test_crlf_file_with_quoted_description_passes(skills_root):
    text = GOOD_SKILL.format(
        name="a-skill", description=f'"Please \\"{TRIGGER}\\" now"', trigger=TRIGGER
    ).replace("\n", "\r\n")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify(skill)["status"] == "PASS"


def test_single_quoted_description_is_unwrapped(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=f"'{TRIGGER}'", trigger=TRIGGER)
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify(skill)["status"] == "PASS"


def test_directory_name_with_spaces_in_path_still_matches(tmp_path):
    root = tmp_path / "my skills root"
    root.mkdir()
    skill = make_skill(root, "a-skill")
    assert verify(skill)["status"] == "PASS"


def test_missing_skill_file_raises(tmp_path):
    with pytest.raises(skillify.SkillifyError, match="no SKILL.md"):
        skillify.resolve_skill_file(tmp_path / "nope")


def test_unreadable_skill_file_raises(skills_root):
    directory = skills_root / "bin"
    directory.mkdir()
    (directory / "SKILL.md").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(skillify.SkillifyError, match="cannot read"):
        verify(directory)


def test_blank_and_indented_lines_in_frontmatter_are_tolerated(skills_root):
    text = (
        f"---\n\n  stray: indented before any key\nname: a-skill\n\n"
        f"description: {TRIGGER}\nmetadata:\n  nested: value\n---\n"
    )
    good = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    body = good.split("---\n", 2)[2]
    skill = make_skill(skills_root, "a-skill", body=text + body)
    assert verify(skill)["status"] == "PASS"


def approval_only_in(section):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("Ask for approval before publishing it.", "Publish it.")
    text = text.replace("Publishing without approval.", "Publishing blindly.")
    return text.replace(f"## {section}\n", f"## {section}\n\nConfirm with the user first.\n", 1)


@pytest.mark.parametrize("section", ["Verification", "Pitfalls", "Anti-patterns", "Contract"])
def test_approval_word_outside_procedure_does_not_count(skills_root, section):
    skill = make_skill(skills_root, "a-skill", body=approval_only_in(section))
    assert failed(verify(skill, external=True)) == {"approval_gate_present"}


def test_approval_word_in_unnumbered_procedure_prose_does_not_count(skills_root):
    text = approval_only_in("Procedure")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify(skill, external=True)) == {"approval_gate_present"}


def test_approval_in_wrapped_numbered_step_counts(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace(
        "Ask for approval before publishing it.",
        "Show the draft,\n   get approval, then publish it.",
    )
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify(skill, external=True)["status"] == "PASS"


def test_approval_in_fenced_example_does_not_count(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace(
        "2. Write the note. Ask for approval before publishing it.",
        "2. Write the note.\n```text\n3. get approval\n```",
    )
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify(skill, external=True)) == {"approval_gate_present"}


def test_missing_procedure_fails_approval_check(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("## Procedure", "## Steps")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert {"section_procedure", "approval_gate_present"} <= failed(verify(skill, external=True))


def verify_recovery(path):
    return skillify_verify.verify_skill(
        skillify.resolve_skill_file(path), TRIGGER, False, recovery_paths=True
    )


def test_recovery_path_marked_optional_passes(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("1. Read the input.", "1. Read the input. Optional: retry once.")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify_recovery(skill)["status"] == "PASS"


def test_recovery_word_in_step_passes(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("1. Read the input.", "1. Read the input. On error use the recovery path.")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert verify_recovery(skill)["status"] == "PASS"


def test_recovery_required_but_unmarked_fails(skills_root):
    skill = make_skill(skills_root, "a-skill")
    assert failed(verify_recovery(skill)) == {"recovery_path_marked"}


def test_recovery_word_only_in_pitfalls_fails(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("Path with spaces", "Optional recovery note")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify_recovery(skill)) == {"recovery_path_marked"}


def test_duplicate_required_section_uses_first(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("| CRLF line endings | Read as text |\n", "")
    text += "\n## Pitfalls\n\n- extra one\n- extra two\n- extra three\n"
    skill = make_skill(skills_root, "a-skill", body=text)
    assert failed(verify(skill)) == {"items_pitfalls"}


HOST_DESCRIPTION = "description: Route requests. Use when you say `ingest a meeting transcript`."
HOST_SKILL = """---
name: host-skill
description: Route requests. Use when you say `ingest a meeting transcript`.
---

# Host Skill

## Quick Start

Intro.

## Process

### Phase 1

1. Read the request.
2. Optional recovery: when nothing matches, list skills.
3. Ask for approval before publishing anything.

## Notes

Free-form.
"""


def verify_patch(path, external=False, recovery=False, trigger=TRIGGER):
    return skillify_verify.verify_skill(
        skillify.resolve_skill_file(path), trigger, external, recovery, mode="patch"
    )


def test_patch_mode_accepts_host_layout_that_create_mode_rejects(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    assert verify(skill)["status"] == "FAIL"
    result = verify_patch(skill)
    assert (result["status"], result["mode"], result["failures"]) == ("PASS", "patch", [])


def test_patch_mode_skips_description_lead_and_sections(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    ids = {c["id"] for c in verify_patch(skill)["checks"]}
    assert ids == {
        "name_kebab_case",
        "name_matches_directory",
        "description_present",
        "description_has_trigger",
        "no_source_only_tool_names",
    }


def test_patch_mode_uses_process_section_for_gates(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    assert verify_patch(skill, external=True, recovery=True)["status"] == "PASS"


def test_patch_mode_prefers_procedure_over_process(skills_root):
    body = HOST_SKILL + "\n## Procedure\n\n1. Plain step.\n"
    skill = make_skill(skills_root, "host-skill", body=body)
    assert failed(verify_patch(skill, external=True)) == {"approval_gate_present"}


def test_patch_mode_fails_missing_gate_in_process(skills_root):
    body = HOST_SKILL.replace("Ask for approval before", "Run")
    body = body.replace("Optional recovery", "Fallback")
    skill = make_skill(skills_root, "host-skill", body=body)
    assert failed(verify_patch(skill, external=True, recovery=True)) == {
        "approval_gate_present",
        "recovery_path_marked",
    }


def test_patch_mode_fails_without_any_procedure_or_process(skills_root):
    body = HOST_SKILL.replace("## Process", "## Flow")
    skill = make_skill(skills_root, "host-skill", body=body)
    assert failed(verify_patch(skill, external=True)) == {"approval_gate_present"}


def test_create_mode_ignores_process_section(skills_root):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    text = text.replace("## Procedure", "## Process")
    skill = make_skill(skills_root, "a-skill", body=text)
    assert {"section_procedure", "approval_gate_present"} <= failed(verify(skill, external=True))


def test_patch_mode_still_fails_name_description_and_tool_names(skills_root):
    body = HOST_SKILL.replace("name: host-skill", "name: Host_Skill")
    body = body.replace(HOST_DESCRIPTION, "description:")
    skill = make_skill(skills_root, "host-skill", body=body + "\nCall skill_manage().\n")
    assert failed(verify_patch(skill)) == {
        "name_kebab_case",
        "name_matches_directory",
        "description_present",
        "description_has_trigger",
        "no_source_only_tool_names",
    }


def test_unknown_mode_raises(skills_root):
    skill = make_skill(skills_root, "a-skill")
    with pytest.raises(skillify.SkillifyError, match="mode"):
        skillify_verify.verify_skill(skill, TRIGGER, False, mode="bogus")


def test_patch_mode_requires_trigger_anywhere_in_description(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    assert verify_patch(skill)["status"] == "PASS"
    assert failed(verify_patch(skill, trigger="triage a flaky test")) == {"description_has_trigger"}
    assert failed(verify_patch(skill, trigger=" ")) == {"description_has_trigger"}


def test_patch_mode_trigger_may_sit_past_the_lead_window(skills_root):
    body = HOST_SKILL.replace("Route requests.", "x " * 150 + "Route requests.")
    skill = make_skill(skills_root, "host-skill", body=body)
    assert verify_patch(skill)["status"] == "PASS"
    assert "description_leads_with_trigger" not in {c["id"] for c in verify_patch(skill)["checks"]}


@pytest.mark.parametrize("heading", ["Process Overview", "Process: Progressive Disclosure"])
def test_patch_mode_accepts_process_prefixed_section(skills_root, heading):
    body = HOST_SKILL.replace("## Process", f"## {heading}")
    skill = make_skill(skills_root, "host-skill", body=body)
    assert verify_patch(skill, external=True, recovery=True)["status"] == "PASS"


def test_patch_mode_does_not_treat_processing_as_process(skills_root):
    body = HOST_SKILL.replace("## Process", "## Processing Notes")
    skill = make_skill(skills_root, "host-skill", body=body)
    assert failed(verify_patch(skill, external=True)) == {"approval_gate_present"}
