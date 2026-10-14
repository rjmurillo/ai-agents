"""Bypasses found by the final review probes, each failing before the fix.

verify is a read-back lint for skills written by this procedure, not a sandbox
against a hostile author. It reads CommonMark basics only.
"""

from __future__ import annotations

import pytest
import skillify
import skillify_text
import skillify_verify
from skill_fixtures import GOOD_SKILL, make_skill

TRIGGER = "ingest a meeting transcript"
GOOD_PROC = (
    "1. Read the input.\n"
    "2. Show the draft and ask the user to approve it (approval).\n"
    "3. Publish the note (external).\n"
)


def body_with(procedure=GOOD_PROC, before=""):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    head, rest = text.split("## Procedure\n", 1)
    tail = rest.split("## Anti-patterns", 1)[1]
    return head + before + "## Procedure\n\n" + procedure + "\n## Anti-patterns" + tail


def result_for(skills_root, body, mode="create"):
    skill = make_skill(skills_root, "a-skill", body=body)
    return skillify_verify.verify_skill(
        skillify.resolve_skill_file(skill), TRIGGER, True, False, mode=mode
    )


def failures(skills_root, body, mode="create"):
    return set(result_for(skills_root, body, mode)["failures"])


def test_clean_skill_passes_every_check(skills_root):
    assert failures(skills_root, body_with()) == set()
    assert failures(skills_root, body_with(), "patch") == set()


# 1. whole-body backstop
@pytest.mark.parametrize("heading", ["Setup", "Procedure (cont.)", "Rollout", "Notes"])
def test_numbered_action_in_another_section_fails(skills_root, heading):
    before = f"## {heading}\n\n1. Push the branch to origin.\n\n"
    assert "external_outside_steps" in failures(skills_root, body_with(before=before))


def test_action_in_other_section_fails_in_patch_mode_too(skills_root):
    before = "## Setup\n\n1. Push the branch to origin.\n\n"
    assert "external_outside_steps" in failures(skills_root, body_with(before=before), "patch")


def test_outside_message_says_move_into_a_numbered_procedure_step(skills_root):
    before = "## Setup\n\n1. Push the branch.\n\n"
    detail = next(
        c["detail"]
        for c in result_for(skills_root, body_with(before=before))["checks"]
        if c["id"] == "external_outside_steps"
    )
    assert "move the action into a numbered Procedure step and tag it" in detail


@pytest.mark.parametrize(
    "section", ["Triggers", "Contract", "Anti-patterns", "Pitfalls", "Verification"]
)
def test_descriptive_sections_are_not_scanned(skills_root, section):
    text = body_with().replace(f"## {section}\n", f"## {section}\n\n- Never push or publish.\n", 1)
    assert failures(skills_root, text) == set()


def test_subsection_of_a_descriptive_section_is_not_scanned(skills_root):
    text = body_with().replace("## Pitfalls\n", "## Pitfalls\n\n### Notes\n\nDo not push.\n", 1)
    assert failures(skills_root, text) == set()


def test_framing_text_under_the_title_is_not_scanned(skills_root):
    text = body_with().replace("Framing paragraph.", "Framing: this skill posts nothing.")
    assert failures(skills_root, text) == set()


def test_fenced_code_in_another_section_is_real_code_and_skipped(skills_root):
    before = "## Setup\n\n```bash\ngit push\n```\n\n"
    assert "external_outside_steps" not in failures(skills_root, body_with(before=before))


def test_action_in_a_subsection_of_another_section_fails(skills_root):
    before = "## Setup\n\n### Details\n\nThen publish it.\n\n"
    assert "external_outside_steps" in failures(skills_root, body_with(before=before))


def test_action_in_a_heading_outside_steps_fails(skills_root):
    before = "## Publish the release\n\ntext\n\n"
    assert "external_outside_steps" in failures(skills_root, body_with(before=before))


def test_tags_not_required_without_external_actions_in_other_sections(skills_root):
    skill = make_skill(
        skills_root, "a-skill", body=body_with(before="## Setup\n\n1. Push the branch.\n\n")
    )
    result = skillify_verify.verify_skill(skillify.resolve_skill_file(skill), TRIGGER, False)
    assert result["status"] == "PASS"


# 2. fences per CommonMark basics
def classify(*lines):
    return skillify_text.line_kinds(list(lines))


def test_tilde_fence_is_not_closed_by_a_backtick_line():
    kinds = classify("~~~", "```", "x", "~~~", "after")
    assert kinds == ["marker", "content", "content", "marker", "text"]


def test_shorter_closing_run_does_not_close():
    assert classify("````", "```", "x", "````", "y") == [
        "marker",
        "content",
        "content",
        "marker",
        "text",
    ]


def test_closing_fence_with_info_string_does_not_close():
    kinds = classify("```text", "a", "```md", "b", "```", "c")
    assert kinds == ["marker", "content", "content", "content", "marker", "text"]


def test_four_space_indent_never_opens_a_fence():
    assert classify("    ```", "x", "    ```") == ["text", "text", "text"]


def test_tab_indent_counts_as_four_columns():
    assert classify("\t```", "x") == ["text", "text"]


def test_four_space_indent_inside_a_fence_does_not_close_it():
    assert classify("```", "    ```", "x", "```", "y") == [
        "marker",
        "content",
        "content",
        "marker",
        "text",
    ]


def test_three_space_indent_still_opens_and_closes():
    assert classify("   ```", "x", "   ```") == ["marker", "content", "marker"]


def test_inline_triple_backticks_are_not_a_fence():
    assert classify("```x``` is inline", "text") == ["text", "text"]


def test_tilde_info_string_may_contain_a_backtick():
    assert classify("~~~ a`b", "x", "~~~") == ["marker", "content", "marker"]


def test_unclosed_fence_runs_to_the_end():
    assert classify("```", "a", "b") == ["marker", "content", "content"]


def test_tilde_desync_cannot_hide_a_second_procedure(skills_root):
    hide = "~~~\n```\n~~~\n\n"
    body = body_with(before=hide + "## Procedure\n\n1. Publish the note now.\n\n")
    assert "single_step_section" in failures(skills_root, body)


def test_indented_fence_cannot_hide_a_second_procedure(skills_root):
    hide = "    ```\n\n## Procedure\n\n1. Publish the note now.\n\n    ```\n\n"
    assert "single_step_section" in failures(skills_root, body_with(before=hide))


def test_inline_fence_decoy_cannot_flip_fence_state(skills_root):
    decoy = "## Notes\n\n```x``` is inline code.\n\n"
    tail = "\n```\n## Procedure\n\n1. (approval) Ask.\n```\n\n```y``` inline.\n"
    steps = "1. Publish the note (external).\n2. Ask the user (approval).\n" + tail
    assert "approval_gate_present" in failures(skills_root, body_with(steps, before=decoy))


# 3. setext headings
def test_setext_procedure_heading_counts_as_a_second_step_section(skills_root):
    setext = "Procedure\n=========\n\n1. Publish the note.\n2. Ask (approval).\n\n"
    assert "single_step_section" in failures(skills_root, body_with(before=setext))


def test_setext_level_two_heading_splits_sections():
    sections = skillify_text.split_sections("Intro\n---\n\ntext\n\nNext\n===\n\nmore\n")
    assert [s.name for s in sections] == ["intro", "next"]
    assert sections[0].lines == ("", "text", "")


def test_rule_after_blank_line_is_not_a_heading():
    assert [s.name for s in skillify_text.split_sections("## A\n\ntext\n\n---\n\nmore\n")] == ["a"]


def test_rule_directly_under_a_list_item_or_quote_is_not_a_heading():
    for first in ("- item", "1. item", "> quote", "| a | b |", "# Real"):
        names = [s.name for s in skillify_text.split_sections(f"{first}\n---\n")]
        assert names in ([], ["real"]), first


def test_multi_line_paragraph_before_underline_is_not_a_title():
    assert skillify_text.split_sections("line one\nline two\n---\n") == []


def test_setext_title_in_a_fence_is_ignored():
    assert skillify_text.split_sections("```\nTitle\n=====\n```\n") == []


def test_indented_title_over_underline_is_not_a_heading():
    assert skillify_text.split_sections("    Title\n=====\n") == []


def test_underline_without_a_title_line_is_ignored():
    assert skillify_text.split_sections("===\n---\n") == []


def test_title_on_last_line_is_not_a_heading():
    assert skillify_text.split_sections("Title") == []


def test_frontmatter_delimiter_is_not_taken_as_a_heading(skills_root):
    assert failures(skills_root, body_with()) == set()


# 4. numbering
@pytest.mark.parametrize(
    "steps",
    [
        "2. Ask (approval).\n1. Publish it (external).\n",
        "3) Publish it (external).\n1) Ask (approval).\n",
        "1. Ask (approval).\n3. Publish it (external).\n",
        "1. Ask (approval).\n1. Publish it (external).\n",
        "2. Ask (approval).\n3. Publish it (external).\n",
    ],
)
def test_out_of_order_numbering_fails(skills_root, steps):
    assert "steps_numbered_in_order" in failures(skills_root, body_with(steps))


def test_in_order_paren_numbering_passes(skills_root):
    steps = "1) Ask (approval).\n2) Publish it (external).\n"
    assert failures(skills_root, body_with(steps)) == set()


def test_numbering_is_checked_in_create_mode_without_external_actions(skills_root):
    skill = make_skill(skills_root, "a-skill", body=body_with("2. One.\n1. Two.\n"))
    path = skillify.resolve_skill_file(skill)
    assert skillify_verify.verify_skill(path, TRIGGER, False)["failures"] == [
        "steps_numbered_in_order"
    ]
    patched = skillify_verify.verify_skill(path, TRIGGER, False, mode="patch")
    assert "steps_numbered_in_order" not in {c["id"] for c in patched["checks"]}


def test_numbering_failure_reports_the_numbers_found(skills_root):
    detail = next(
        c["detail"]
        for c in result_for(skills_root, body_with("2. A (approval).\n1. B (external).\n"))[
            "checks"
        ]
        if c["id"] == "steps_numbered_in_order"
    )
    assert "[2, 1]" in detail


# 5. tag hygiene
APPROVAL_ONLY_HIDDEN = [
    "1. Note it <!-- (approval) -->\n2. Publish the note (external).\n",
    "1. Lint with `lint --tag (approval)`.\n2. Publish the note (external).\n",
    "1. Lint the files:\n\n       echo '(approval)'\n\n2. Publish the note (external).\n",
    "1. Lint.\n```text\n(approval)\n```\n2. Publish the note (external).\n",
    "1. Lint.\n<!--\n(approval)\n-->\n2. Publish the note (external).\n",
    "1. Lint with ``a ` (approval) b``.\n2. Publish the note (external).\n",
]


@pytest.mark.parametrize("steps", APPROVAL_ONLY_HIDDEN)
def test_approval_tag_in_hidden_context_does_not_count(skills_root, steps):
    result = result_for(skills_root, body_with(steps))
    assert "approval_gate_present" in result["failures"]


def test_approval_tag_in_plain_prose_counts(skills_root):
    steps = "1. Ask the user to approve `the draft` (approval).\n2. Publish it (external).\n"
    assert failures(skills_root, body_with(steps)) == set()


def test_single_line_html_comment_with_text_around_it_keeps_the_prose(skills_root):
    steps = "1. Ask <!-- note --> the user (approval).\n2. Publish it (external).\n"
    assert failures(skills_root, body_with(steps)) == set()


def test_external_tag_counts_anywhere(skills_root):
    for steps in (
        "1. Ask (approval).\n2. Run it `x (external)`.\n",
        "1. Ask (approval).\n2. Run it <!-- (external) -->.\n",
        "1. Ask (approval).\n2. Run it.\n```\n(external)\n```\n",
    ):
        assert failures(skills_root, body_with(steps)) == set(), steps


def test_comment_close_line_text_is_comment_content():
    parsed = skillify_text.parse_steps(["1. Go <!--", "hidden --> tail", "2. Next."])
    assert [s.number for s in parsed.steps] == [1, 2]
    assert "hidden" in parsed.steps[0].fenced and "hidden" not in parsed.steps[0].text


def test_comment_before_first_step_is_loose():
    parsed = skillify_text.parse_steps(["<!--", "push it", "-->", "1. Go."])
    assert "push it" in parsed.loose
    assert [s.number for s in parsed.steps] == [1]


def test_comment_open_and_close_on_the_same_line_is_plain_text():
    parsed = skillify_text.parse_steps(["1. A <!-- x --> b.", "2. C."])
    assert [s.number for s in parsed.steps] == [1, 2]
    assert "b." in parsed.steps[0].text


def test_blank_line_inside_a_comment_keeps_it_open():
    parsed = skillify_text.parse_steps(["1. A <!--", "", "x", "-->", "2. B."])
    assert "x" in parsed.steps[0].fenced and parsed.steps[0].text.endswith("<!--")


def test_approval_prose_strips_comments_and_code():
    assert skillify_text.approval_prose("a <!-- (approval) --> `(approval)` b") == "a   b"


def test_outside_step_lines_without_a_step_section_scans_other_sections():
    body = "# T\n\nintro\n\n## Setup\n\ndo it\n\n## Pitfalls\n\nskip\n"
    assert skillify_text.outside_step_lines(body, False) == ["## Setup", "do it"]


def test_outside_step_lines_process_family_is_the_step_section_in_patch_mode():
    body = "## Process Overview\n\n1. a\n\n## Notes\n\nb\n"
    assert skillify_text.outside_step_lines(body, True) == ["## Notes", "b"]
    assert skillify_text.outside_step_lines(body, False) == [
        "## Process Overview",
        "1. a",
        "## Notes",
        "b",
    ]


def test_outside_step_lines_no_process_family_scans_everything():
    assert skillify_text.outside_step_lines("## Other\n\nx\n", True) == ["## Other", "x"]


def test_prose_before_the_first_step_is_loose():
    parsed = skillify_text.parse_steps(["intro", "", "1. A", "   more", "", "text", "2. B"])
    assert parsed.loose == ("intro", "text")
    assert "more" in parsed.steps[0].text


def test_detached_lines_stay_loose_until_the_next_numbered_step():
    parsed = skillify_text.parse_steps(["1. A", "", "loose", "still loose", "2. B", "tail"])
    assert parsed.loose == ("loose", "still loose")
    assert [s.number for s in parsed.steps] == [1, 2]
    assert "tail" in parsed.steps[1].text


def test_fence_before_first_step_is_loose_and_after_detach_is_loose():
    parsed = skillify_text.parse_steps(["```", "a", "```", "1. S", "", "loose", "```", "b", "```"])
    assert parsed.loose == ("a", "loose", "b")


def test_four_space_indented_numeral_is_not_a_step():
    parsed = skillify_text.parse_steps(["1. A", "    2. B"])
    assert [s.number for s in parsed.steps] == [1]


def test_indented_code_after_blank_goes_to_code_not_prose():
    parsed = skillify_text.parse_steps(["1. A", "", "       code (approval)"])
    assert "(approval)" in parsed.steps[0].fenced and "(approval)" not in parsed.steps[0].text
