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
3. Ask for approval before publishing anything.
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


def test_approval_after_the_publish_step_fails(skills_root):
    steps = "1. Write the note.\n2. Publish the note.\n3. Get approval.\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


@pytest.mark.parametrize(
    "first",
    ["Force-push the branch to main.", "Enable auto-merge.", "Share results with the team."],
)
def test_late_approval_after_risky_first_step_fails(skills_root, first):
    steps = f"1. {first}\n2. Get approval.\n3. Open a PR.\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_approval_in_earlier_step_passes(skills_root):
    steps = "1. Ask for approval of the draft.\n2. Publish the note.\n"
    assert external_failed(skills_root, steps) == set()


def test_approval_earlier_in_same_step_passes(skills_root):
    assert external_failed(skills_root, "1. Confirm with the user, then push it.\n") == set()


def test_approval_after_verb_in_same_step_fails(skills_root):
    steps = "1. Publish the note after approval.\n"
    assert external_failed(skills_root, steps) == {"approval_gate_present"}


def test_no_external_step_fails_with_naming_message(skills_root):
    skill = make_skill(
        skills_root, "a-skill", body=order_skill("1. Write the note.\n2. Get approval.\n")
    )
    result = verify(skill, external=True)
    check = next(c for c in result["checks"] if c["id"] == "approval_gate_present")
    assert not check["ok"]
    assert "name the external" in check["detail"]


@pytest.mark.parametrize(
    "step",
    [
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
    ],
)
def test_external_verbs_are_recognized(skills_root, step):
    assert external_failed(skills_root, f"1. {step}.\n") == {"approval_gate_present"}


@pytest.mark.parametrize(
    "step",
    [
        "Postgres is read",
        "Prepare the release notes",
        "Use the shared cache",
        "Resolve merge conflicts",
        "Write the release note",
        "Load the shared utils",
    ],
)
def test_non_verbs_are_not_external(skills_root, step):
    steps = f"1. {step}.\n2. Get approval.\n"
    check = next(
        c
        for c in verify(make_skill(skills_root, "a-skill", body=order_skill(steps)), external=True)[
            "checks"
        ]
        if c["id"] == "approval_gate_present"
    )
    assert "name the external" in check["detail"]


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
