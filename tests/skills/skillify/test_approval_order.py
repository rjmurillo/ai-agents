"""Approval must come before the first external action in a numbered step."""

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
3. Ask for approval before publishing anything (external).
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


def test_approval_after_the_tagged_step_fails(skills_root):
    steps = "1. Write the note.\n2. Publish the note (external).\n3. Get approval.\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_approval_in_earlier_step_passes(skills_root):
    steps = "1. Ask for approval of the draft.\n2. Publish the note (external).\n"
    assert external_failed(skills_root, steps) == set()


def test_approval_earlier_in_same_step_passes(skills_root):
    steps = "1. Confirm with the user, then push it (external).\n"
    assert external_failed(skills_root, steps) == set()


def test_approval_after_tag_in_same_step_fails(skills_root):
    steps = "1. Publish the note (external) after approval.\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_later_tagged_steps_are_covered_by_earlier_approval(skills_root):
    steps = (
        "1. Ask for approval of the draft.\n2. Publish the note (external).\n"
        "3. Notify the owner (external).\n"
    )
    assert external_failed(skills_root, steps) == set()


def test_approval_before_step_two_but_not_before_tagged_step_one_fails(skills_root):
    steps = "1. Prepare it (external).\n2. Get approval.\n3. Check it.\n4. Ship it (external).\n"
    check = check_of(run_steps(skills_root, steps), "approval_gate_present")
    assert not check["ok"]
    assert "step 1" in check["detail"]


def test_failure_names_the_tagged_step_that_lacks_approval(skills_root):
    steps = "1. Draft it (external) after approval.\n2. Send it (external).\n"
    detail = check_of(run_steps(skills_root, steps), "approval_gate_present")["detail"]
    assert "step 1" in detail


def test_each_tagged_step_is_checked_in_order(skills_root):
    steps = "1. Get approval.\n2. Send it (external).\n3. Upload it (external).\n"
    assert external_failed(skills_root, steps) == set()
    steps = "1. Get approval.\n2. Upload it.\n3. Send it (external).\n"
    assert external_failed(skills_root, steps) == {"external_step_untagged"}


def test_no_tagged_step_fails_with_tag_message(skills_root):
    result = run_steps(skills_root, "1. Write the note.\n2. Get approval.\n")
    check = check_of(result, "approval_gate_present")
    assert not check["ok"]
    assert "tag each external step with (external)" in check["detail"]


def test_tag_is_case_insensitive_and_position_free(skills_root):
    steps = "1. Get approval.\n2. (EXTERNAL) Publish the note.\n3. Mail it (External).\n"
    assert external_failed(skills_root, steps) == set()


def test_tag_only_step_without_verb_match_passes_when_approval_first(skills_root):
    steps = "1. Get approval.\n2. Run the thing with the vendor tool (external).\n"
    assert external_failed(skills_root, steps) == set()


def test_tag_only_step_without_approval_fails(skills_root):
    steps = "1. Run the thing with the vendor tool (external).\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_untagged_matched_step_fails_loudly_with_step_number(skills_root):
    steps = "1. Get approval.\n2. Publish the note (external).\n3. Reopen the PR.\n"
    result = run_steps(skills_root, steps)
    check = check_of(result, "external_step_untagged")
    assert not check["ok"]
    assert "step 3" in check["detail"]
    assert "(external)" in check["detail"] and "reword" in check["detail"]
    assert {"external_step_untagged"} == set(result["failures"])


def test_untagged_check_lists_every_step(skills_root):
    steps = "1. Get approval.\n2. Deploy it.\n3. Publish it (external).\n4. Announce it.\n"
    detail = check_of(run_steps(skills_root, steps), "external_step_untagged")["detail"]
    assert "step 2, 4" in detail


def test_untagged_check_passes_and_is_silent_when_all_matched_steps_are_tagged(skills_root):
    result = run_steps(skills_root, "1. Get approval.\n2. Publish it (external).\n")
    assert check_of(result, "external_step_untagged")["ok"]


def test_tags_are_not_required_when_audit_has_no_external_actions(skills_root):
    skill = make_skill(skills_root, "a-skill", body=order_skill("1. Publish the note.\n"))
    result = verify(skill, external=False)
    assert "external_step_untagged" not in {c["id"] for c in result["checks"]}
    assert result["status"] == "PASS"


def test_approval_word_inside_a_tag_does_not_count(skills_root):
    steps = "1. Publish it (external approved).\n"
    result = run_steps(skills_root, steps)
    assert not check_of(result, "approval_gate_present")["ok"]


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
        result = run_steps(skills_root, f"1. Get approval.\n2. {step}.\n")
        assert not check_of(result, "external_step_untagged")["ok"], step


def test_messages_mention_process_only_in_patch_mode(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)

    def details(result):
        return " ".join(
            c["detail"] for c in result["checks"] if c["id"] != "name_matches_directory"
        )

    create = verify(skill, external=True)
    assert "(or Process)" not in details(create)
    patch = skillify_verify.verify_skill(
        skillify.resolve_skill_file(skill), TRIGGER, True, True, mode="patch"
    )
    assert "(or Process)" in " ".join(c["detail"] for c in patch["checks"])
    bad = HOST_SKILL.replace("Ask for approval before", "Run").replace("Optional recovery", "Fall")
    skill2 = make_skill(skills_root, "host-skill", body=bad)
    create_fail = skillify_verify.verify_skill(
        skillify.resolve_skill_file(skill2), TRIGGER, True, True
    )
    patch_fail = skillify_verify.verify_skill(
        skillify.resolve_skill_file(skill2), TRIGGER, True, True, mode="patch"
    )
    create_msgs = [c["detail"] for c in create_fail["checks"] if not c["ok"]]
    patch_msgs = [c["detail"] for c in patch_fail["checks"] if c["id"] == "recovery_path_marked"]
    assert not any("(or Process)" in m for m in create_msgs)
    assert "(or Process)" in patch_msgs[0]


def verify_patch(path):
    return skillify_verify.verify_skill(
        skillify.resolve_skill_file(path), TRIGGER, True, False, mode="patch"
    )


def test_patch_mode_applies_tag_rules_to_the_process_section(skills_root):
    skill = make_skill(skills_root, "host-skill", body=HOST_SKILL)
    assert verify_patch(skill)["status"] == "PASS"


def test_patch_mode_process_untagged_step_fails(skills_root):
    body = HOST_SKILL + "4. Reopen the PR.\n"
    skill = make_skill(skills_root, "host-skill", body=body)
    assert failed(verify_patch(skill)) == {"external_step_untagged"}


def test_patch_mode_process_tag_without_approval_fails(skills_root):
    body = HOST_SKILL.replace("Ask for approval before", "Go on")
    skill = make_skill(skills_root, "host-skill", body=body)
    result = verify_patch(skill)
    assert failed(result) == {"approval_gate_present"}
    assert "Procedure (or Process)" not in check_of(result, "approval_gate_present")["detail"]


def test_patch_mode_no_tag_message_names_process(skills_root):
    body = HOST_SKILL.replace(" (external)", "")
    skill = make_skill(skills_root, "host-skill", body=body)
    detail = check_of(verify_patch(skill), "approval_gate_present")["detail"]
    assert "Procedure (or Process)" in detail


def test_create_mode_no_tag_message_names_procedure_only(skills_root):
    result = run_steps(skills_root, "1. Write the note.\n")
    detail = check_of(result, "approval_gate_present")["detail"]
    assert "Procedure step" in detail and "Process" not in detail
