"""The (approval) tag must come strictly before every (external) step."""

from __future__ import annotations

import pytest
import skillify
import skillify_verify
from skill_fixtures import GOOD_SKILL, make_skill

TRIGGER = "ingest a meeting transcript"
HOST_SKILL = """---
name: host-skill
description: Route requests. Use when you say `ingest a meeting transcript`.
---

## Process

1. Read the request.
2. Optional recovery: when nothing matches, list skills.
3. Ask the user to approve the draft (approval).
4. Publish anything (external).
"""


def verify(path, external=False):
    return skillify_verify.verify_skill(skillify.resolve_skill_file(path), TRIGGER, external)


def failed(result):
    return set(result["failures"])


def order_skill(procedure):
    text = GOOD_SKILL.format(name="a-skill", description=TRIGGER, trigger=TRIGGER)
    head, rest = text.split("## Procedure\n", 1)
    tail = rest.split("## Anti-patterns", 1)[1]
    return head + "## Procedure\n\n" + procedure + "\n## Anti-patterns" + tail


def external_failed(skills_root, procedure):
    skill = make_skill(skills_root, "a-skill", body=order_skill(procedure))
    return failed(verify(skill, external=True))


def check_of(result, check_id):
    return next(c for c in result["checks"] if c["id"] == check_id)


def run_steps(skills_root, steps):
    skill = make_skill(skills_root, "a-skill", body=order_skill(steps))
    return verify(skill, external=True)


def gate(skills_root, steps):
    return check_of(run_steps(skills_root, steps), "approval_gate_present")


def test_approval_step_before_external_step_passes(skills_root):
    steps = "1. Ask the user to approve the draft (approval).\n2. Publish the note (external).\n"
    assert external_failed(skills_root, steps) == set()


def test_external_step_before_any_approval_step_fails(skills_root):
    steps = "1. Publish the note (external).\n2. Ask the user to approve (approval).\n"
    check = gate(skills_root, steps)
    assert not check["ok"]
    assert check["detail"] == (
        "step 1 ('Publish the note (external).') is tagged (external) "
        "but no (approval) step comes before it"
    )


def test_approval_before_step_two_but_external_at_step_one_fails(skills_root):
    steps = "1. Prepare it (external).\n2. Ask the user (approval).\n3. Send it (external).\n"
    assert "step 1 ('Prepare it (external).') is tagged" in gate(skills_root, steps)["detail"]


def test_two_external_steps_share_one_earlier_approval(skills_root):
    steps = (
        "1. Ask the user to approve the plan (approval).\n2. Publish the note (external).\n"
        "3. Notify the owner (external).\n"
    )
    assert external_failed(skills_root, steps) == set()


def test_second_external_step_is_checked_on_its_own(skills_root):
    steps = (
        "1. Ask the user (approval).\n2. Publish the note (external).\n"
        "3. Notify the owner (external).\n"
    )
    assert external_failed(skills_root, steps) == set()
    steps = "1. Prepare it (external).\n2. Ask the user (approval).\n3. Send it (external).\n"
    assert not gate(skills_root, steps)["ok"]


def test_approval_tag_in_the_same_step_does_not_count(skills_root):
    steps = "1. Ask the user to approve (approval), then publish it (external).\n"
    assert "tagged both" in gate(skills_root, steps)["detail"]


def test_trailing_approval_tag_same_step_bypass_is_closed(skills_root):
    steps = "1. Publish the note (external) after asking the user (approval).\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_both_tags_on_one_step_fails_even_after_a_real_approval(skills_root):
    steps = "1. Ask the user (approval).\n2. Publish it (external) (approval).\n"
    check = gate(skills_root, steps)
    assert not check["ok"]
    assert check["detail"] == (
        "step 2 ('Publish it (external) (approval).') is tagged both (external) and (approval); "
        "split it"
    )


def test_approval_words_without_the_tag_do_not_satisfy_the_gate(skills_root):
    steps = "1. Do not wait for approval.\n2. Publish the note (external).\n"
    check = gate(skills_root, steps)
    assert not check["ok"]
    assert check["detail"] == "tag the step that asks the user with (approval)"


def test_approval_tag_without_external_step_fails_with_tag_message(skills_root):
    check = gate(skills_root, "1. Ask the user (approval).\n2. Write the note.\n")
    assert "tag each external step with (external)" in check["detail"]


def test_tags_are_case_insensitive_and_position_free(skills_root):
    steps = "1. (APPROVAL) Ask the user.\n2. (EXTERNAL) Publish the note.\n3. Mail it (External).\n"
    assert external_failed(skills_root, steps) == set()


def test_tag_only_step_without_verb_match_passes_when_approved_first(skills_root):
    steps = "1. Ask the user (approval).\n2. Run the vendor tool (external).\n"
    assert external_failed(skills_root, steps) == set()


def test_tag_only_step_without_approval_step_fails(skills_root):
    check = gate(skills_root, "1. Run the vendor tool (external).\n")
    assert check["detail"] == "tag the step that asks the user with (approval)"


def test_untagged_matched_step_fails_loudly_with_step_number(skills_root):
    steps = "1. Ask the user (approval).\n2. Publish the note (external).\n3. Reopen the PR.\n"
    result = run_steps(skills_root, steps)
    check = check_of(result, "external_step_untagged")
    assert not check["ok"]
    assert "step 3" in check["detail"]
    assert "(external)" in check["detail"] and "reword" in check["detail"]
    assert set(result["failures"]) == {"external_step_untagged"}


def test_untagged_check_lists_every_step(skills_root):
    steps = "1. Ask (approval).\n2. Deploy it.\n3. Publish it (external).\n4. Announce it.\n"
    detail = check_of(run_steps(skills_root, steps), "external_step_untagged")["detail"]
    assert "step 2 ('Deploy it.'); step 4 ('Announce it.')" in detail


def test_untagged_check_passes_when_every_matched_step_is_tagged(skills_root):
    result = run_steps(skills_root, "1. Ask (approval).\n2. Publish it (external).\n")
    assert check_of(result, "external_step_untagged")["ok"]


def test_tags_are_not_required_when_audit_has_no_external_actions(skills_root):
    skill = make_skill(skills_root, "a-skill", body=order_skill("1. Publish the note.\n"))
    result = verify(skill, external=False)
    ids = {c["id"] for c in result["checks"]}
    assert not ids & {"external_step_untagged", "external_outside_steps"}
    assert result["status"] == "PASS"


FENCE_PUBLISH = "1. Run the release script.\n```bash\ngh pr merge --admin\n```\n"


def test_fenced_command_under_untagged_step_fails(skills_root):
    result = run_steps(skills_root, FENCE_PUBLISH)
    assert not check_of(result, "external_step_untagged")["ok"]
    assert "step 1" in check_of(result, "external_step_untagged")["detail"]


@pytest.mark.parametrize("command", ["git push origin main", "npm publish", "curl -X POST --send"])
def test_fenced_push_or_publish_is_seen_by_the_backstop(skills_root, command):
    steps = f"1. Ask the user (approval).\n2. Release it.\n```\n{command}\n```\n"
    assert not check_of(run_steps(skills_root, steps), "external_step_untagged")["ok"]


def test_fenced_command_under_tagged_step_after_approval_passes(skills_root):
    steps = (
        "1. Ask the user to approve (approval).\n"
        "2. Merge the change (external).\n```bash\ngh pr merge --admin\n```\n"
    )
    assert external_failed(skills_root, steps) == set()


def test_fence_does_not_start_a_new_step(skills_root):
    steps = "1. Ask the user (approval).\n```text\n2. Publish it (external).\n```\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}
    # The fenced "2." stays inside step 1, so step 1 carries both tags.
    assert (
        "step 1 ('Ask the user (approval).') is tagged both" in gate(skills_root, steps)["detail"]
    )


def test_external_tag_inside_a_fence_makes_the_step_external(skills_root):
    steps = "1. Run the tool.\n```\n(external)\n```\n"
    assert gate(skills_root, steps)["detail"] == "tag the step that asks the user with (approval)"


def test_approval_tag_inside_a_fence_never_counts(skills_root):
    steps = "1. Draft it.\n```text\n(approval)\n```\n2. Publish it (external).\n"
    assert gate(skills_root, steps)["detail"] == "tag the step that asks the user with (approval)"


def test_repeated_procedure_heading_fails_single_step_section(skills_root):
    text = order_skill("1. Write it.\n") + "\n## Procedure\n\n1. Publish it.\n"
    skill = make_skill(skills_root, "a-skill", body=text)
    result = verify(skill)
    assert failed(result) == {"single_step_section"}
    detail = check_of(result, "single_step_section")["detail"]
    assert "2 times" in detail


def test_single_procedure_heading_passes_single_step_section(skills_root):
    skill = make_skill(skills_root, "a-skill", body=order_skill("1. Write it.\n"))
    assert check_of(verify(skill), "single_step_section")["ok"]


def test_repeated_process_family_fails_in_patch_mode(skills_root):
    body = HOST_SKILL + "\n## Process Overview\n\n1. Publish it.\n"
    skill = make_skill(skills_root, "host-skill", body=body)
    assert "single_step_section" in failed(verify_patch(skill))


def test_second_process_is_ignored_in_create_mode(skills_root):
    skill = make_skill(
        skills_root, "a-skill", body=order_skill("1. Write it.\n") + "\n## Process\n\n"
    )
    assert check_of(verify(skill), "single_step_section")["ok"]


def test_process_family_is_ignored_when_procedure_exists_in_patch_mode(skills_root):
    body = HOST_SKILL + "\n## Procedure\n\n1. Write it.\n"
    skill = make_skill(skills_root, "host-skill", body=body)
    assert check_of(verify_patch(skill), "single_step_section")["ok"]


def outside(skills_root, procedure):
    skill = make_skill(skills_root, "a-skill", body=order_skill(procedure))
    return check_of(verify(skill, external=True), "external_outside_steps")


def test_external_action_in_intro_before_step_one_fails(skills_root):
    steps = "First, publish the note to the wiki.\n\n1. Ask (approval).\n2. Write it.\n"
    check = outside(skills_root, steps)
    assert not check["ok"]
    assert "move the action into a numbered Procedure step and tag it" in check["detail"]


def test_external_action_in_loose_paragraph_between_steps_fails(skills_root):
    steps = "1. Ask (approval).\n2. Write it.\n\nThen push the branch.\n\n3. Done.\n"
    assert not outside(skills_root, steps)["ok"]


def test_external_action_in_heading_inside_steps_fails(skills_root):
    steps = "1. Ask (approval).\n\n### Publish\n\n2. Write it.\n"
    assert not outside(skills_root, steps)["ok"]


def test_loose_line_without_external_action_passes(skills_root):
    steps = "Run these in order.\n\n1. Ask (approval).\n2. Write it.\n"
    assert outside(skills_root, steps)["ok"]


def test_fence_before_step_one_is_loose_and_checked(skills_root):
    steps = "```bash\ngit push\n```\n\n1. Write it.\n"
    assert not outside(skills_root, steps)["ok"]


def test_continuation_lines_and_indented_lines_belong_to_the_step(skills_root):
    steps = (
        "1. Ask the user\n   to approve (approval).\n\n   More detail on the step.\n2. Write it.\n"
    )
    assert outside(skills_root, steps)["ok"]
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_wrapped_continuation_carries_the_tag(skills_root):
    steps = (
        "1. Ask the user to approve (approval).\n2. Send the report\n   to the team (external).\n"
    )
    assert external_failed(skills_root, steps) == set()


def test_indented_publish_after_blank_stays_with_its_step_for_the_backstop(skills_root):
    steps = "1. Ask (approval).\n2. Write it.\n\n   Then publish it.\n"
    result = run_steps(skills_root, steps)
    assert not check_of(result, "external_step_untagged")["ok"]
    assert check_of(result, "external_outside_steps")["ok"]


EXTERNAL_PHRASES = [
    "Publishes the page",
    "pushed to origin",
    "Posting a comment",
    "Send the report",
    "Deploy it",
    "Merging the branch",
    "Release the build",
    "Upload the file",
    "Share the link",
    "email the owner",
    "Open a PR",
    "open the pull request",
    "Open an issue",
    "Create a PR",
    "File a ticket",
    "Sent the report",
    "Share it with the team",
    "Share results with the team",
    "Shares the doc",
    "Shared the doc",
    "sharing them",
    "Open a new PR",
    "create a GitHub issue",
    "open a\tPR",
    "Submitted a PR",
    "Filed a bug",
    "Merge queue the PR",
    "Force-push the branch",
    "Enable auto-merge",
    "Re-deploy the service",
    "re-publish the package",
    "cross-post to Slack",
    "Re-open the PR",
    "Creating a PR",
    "Filing a ticket",
    "Raising an issue",
    "Submitting a PR",
    "Open a new draft PR",
    "Create a new GitHub issue",
    "Open PR-42",
    "Open a pull-request",
    "e-mail the owner",
]

PASS3_MISSES = [
    "gh pr create --fill",
    "Run gh issue comment 12",
    "gh pr merge 5",
    "Reopen the PR",
    "Re-open the issue",
    "kubectl apply -f app.yaml",
    "Apply the manifest",
    "automerge the branch",
    "Enable automerge",
    "mail the owner",
    "Open an MR",
    "Open a new draft pull request for the team",
    "Open the one big shared tracking issue",
    "Close the issue",
    "Reply to the thread",
    "Notify the owner",
    "Announce the change",
    "Ship the build",
    "Tag the new release",
    "Tag a release",
]

NON_VERBS = [
    "Postgres is read",
    "Prepare the release notes",
    "Use the shared cache",
    "Resolve merge conflicts",
    "Write the release note",
    "Load the shared utils",
]


@pytest.mark.parametrize("step", EXTERNAL_PHRASES)
def test_external_verbs_are_recognized(step):
    assert skillify_verify.EXTERNAL_RE.search(f"1. {step}.")


@pytest.mark.parametrize("step", PASS3_MISSES)
def test_pass_three_misses_are_recognized(step):
    assert skillify_verify.EXTERNAL_RE.search(step)


@pytest.mark.parametrize("step", NON_VERBS)
def test_non_verbs_are_not_external(step):
    assert not skillify_verify.EXTERNAL_RE.search(f"1. {step}.")


def test_untagged_backstop_catches_each_phrase_list_member(skills_root):
    for step in ("Run gh pr create", "Reopen the PR", "kubectl apply the manifest", "automerge it"):
        result = run_steps(skills_root, f"1. Ask (approval).\n2. {step}.\n")
        assert not check_of(result, "external_step_untagged")["ok"], step


def verify_patch(path, external=True):
    return skillify_verify.verify_skill(
        skillify.resolve_skill_file(path), TRIGGER, external, False, mode="patch"
    )


def test_messages_mention_process_only_in_patch_mode(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    create = skillify_verify.verify_skill(skillify.resolve_skill_file(skill), TRIGGER, True, True)
    assert not any("(or Process)" in c["detail"] for c in create["checks"])
    patch = skillify_verify.verify_skill(
        skillify.resolve_skill_file(skill), TRIGGER, True, True, mode="patch"
    )
    assert "(or Process)" in " ".join(c["detail"] for c in patch["checks"])


def test_patch_mode_applies_tag_rules_to_the_process_section(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    assert verify_patch(skill)["status"] == "PASS"


def test_patch_mode_process_untagged_step_fails(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL + "5. Reopen the PR.\n")
    assert failed(verify_patch(skill)) == {"external_step_untagged"}


def test_patch_mode_process_external_before_approval_fails(skills_root):
    body = HOST_SKILL.replace("3. Ask the user to approve the draft (approval).\n", "")
    body = body.replace("4. Publish", "3. Publish")
    skill = make_skill(skills_root, "host-skill", body=body)
    result = verify_patch(skill)
    assert failed(result) == {"approval_gate_present"}
    assert check_of(result, "approval_gate_present")["detail"].startswith("tag the step")


def test_patch_mode_process_fenced_command_is_seen(skills_root):
    body = HOST_SKILL + "5. Run the script.\n```bash\ngh pr merge --admin\n```\n"
    skill = make_skill(skills_root, "host-skill", body=body)
    assert failed(verify_patch(skill)) == {"external_step_untagged"}


def test_patch_mode_no_tag_message_names_process(skills_root):
    body = HOST_SKILL.replace(" (external)", "")
    skill = make_skill(skills_root, "host-skill", body=body)
    detail = check_of(verify_patch(skill), "approval_gate_present")["detail"]
    assert "Procedure (or Process)" in detail


def test_create_mode_no_tag_message_names_procedure_only(skills_root):
    detail = check_of(run_steps(skills_root, "1. Write the note.\n"), "approval_gate_present")[
        "detail"
    ]
    assert "Procedure step" in detail and "Process" not in detail


def test_label_uses_displayed_numeral_after_a_restart():
    restarted = skillify_verify.Step(number=1, group=1, text="1. Publish the note.", fenced="")
    assert skillify_verify._label(restarted) == "step 1 ('Publish the note.')"


def test_outside_message_names_process_in_patch_mode():
    parsed = skillify_verify.ParsedSteps(steps=(), loose=("Push the branch.",))
    patch = skillify_verify._outside_steps_check(parsed, [], patching=True)
    create = skillify_verify._outside_steps_check(parsed, [], patching=False)
    assert "numbered Procedure (or Process) step" in patch["detail"]
    assert "numbered Procedure step" in create["detail"]


def test_label_keeps_text_without_a_leading_numeral():
    bare = skillify_verify.Step(number=3, group=0, text="Publish the note.", fenced="")
    assert skillify_verify._label(bare) == "step 3 ('Publish the note.')"
