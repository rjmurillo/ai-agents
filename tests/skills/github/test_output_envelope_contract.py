"""Contract test for the canonical github skill output envelope (ADR-056).

Every github skill script that emits JSON to stdout MUST wrap its payload in the
canonical envelope written by ``github_core.output.write_skill_output`` /
``write_skill_error``. The top-level keys MUST be exactly::

    {"Success", "Data", "Error", "Metadata"}

This test runs each script's ``main`` with mocked authentication and subprocess
I/O, captures stdout in ``--output-format json`` mode, parses the last JSON
line, and asserts the top-level key set.

Issue #2388: standardize the github skill output envelope across all scripts.

Residual: the ``pr/`` family is tracked separately and is NOT yet converted;
see ``PR_RESIDUAL`` below. Those scripts are intentionally excluded from the
parametrized run until their consumer fan-out (for example
``wait_for_unresolved_zero`` reading top-level keys from
``get_unresolved_review_threads``) is updated in lockstep.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest
from github_core.api import RepoInfo
from test_helpers import import_skill_script, make_completed_process

CANONICAL_KEYS = {"Success", "Data", "Error", "Metadata"}


@pytest.fixture
def _restore_modules():
    """Restore sys.modules entries import_skill_script overwrites.

    import_skill_script registers the script under both ``skill_<name>`` and the
    bare ``<name>``. Sibling tests (test_utility_scripts) import the same names
    differently and reload them, so this fixture snapshots and restores the
    affected entries to keep tests independent (ADR testing rule 5).
    """
    snapshot = dict(sys.modules)
    try:
        yield
    finally:
        for key in list(sys.modules):
            if key not in snapshot:
                del sys.modules[key]
        sys.modules.update(snapshot)


def _last_json_object(text: str) -> dict:
    """Return the last line of ``text`` that parses as a JSON object."""
    for line in reversed(text.strip().splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"No JSON object found in output: {text!r}")


# Each row: (script_name, subdir, argv, list-of-subprocess-CompletedProcess).
# The subprocess side effects feed the script's gh/git calls in order. argv
# always includes ``--output-format json`` so stdout is pure JSON.
_ISSUE_VIEW = json.dumps(
    {
        "number": 1,
        "title": "T",
        "body": "",
        "state": "OPEN",
        "author": {"login": "a"},
        "labels": [],
        "milestone": None,
        "assignees": [],
        "createdAt": "",
        "updatedAt": "",
    }
)

CONVERTED_SCRIPTS: list[tuple[str, str, list[str], list]] = [
    (
        "get_issue_context",
        "issue",
        ["--owner", "o", "--repo", "r", "--issue", "1", "--output-format", "json"],
        [make_completed_process(stdout=_ISSUE_VIEW)],
    ),
    (
        "new_issue",
        "issue",
        ["--owner", "o", "--repo", "r", "--title", "T", "--output-format", "json"],
        [make_completed_process(stdout="https://github.com/o/r/issues/5\n")],
    ),
    (
        "edit_issue_body",
        "issue",
        ["--owner", "o", "--repo", "r", "--issue", "1", "--body", "b", "--output-format", "json"],
        [make_completed_process(stdout="")],
    ),
    (
        "post_issue_comment",
        "issue",
        ["--owner", "o", "--repo", "r", "--issue", "1", "--body", "b", "--output-format", "json"],
        [make_completed_process(stdout=json.dumps({"id": 100, "html_url": "u"}))],
    ),
    (
        "set_issue_milestone",
        "issue",
        [
            "--owner", "o", "--repo", "r", "--issue", "1",
            "--milestone", "v1.0.0", "--output-format", "json",
        ],
        [
            make_completed_process(stdout="null"),       # _get_current_milestone
            make_completed_process(stdout="v1.0.0"),      # _get_milestone_titles
            make_completed_process(stdout=""),            # assign
        ],
    ),
    (
        "set_item_milestone",
        "milestone",
        [
            "--item-type", "issue", "--item-number", "1",
            "--owner", "o", "--repo", "r",
            "--milestone-title", "v1.0.0", "--output-format", "json",
        ],
        [
            make_completed_process(stdout=json.dumps({"milestone": None})),  # current
            make_completed_process(stdout=""),                               # assign
        ],
    ),
    (
        "get_latest_semantic_milestone",
        "milestone",
        ["--owner", "o", "--repo", "r", "--output-format", "json"],
        [make_completed_process(stdout=json.dumps([{"title": "1.0.0", "number": 1}]))],
    ),
    (
        "add_comment_reaction",
        "reactions",
        [
            "--owner", "o", "--repo", "r", "--comment-id", "1",
            "--reaction", "eyes", "--output-format", "json",
        ],
        [make_completed_process(stdout=json.dumps({"id": 1}))],
    ),
    (
        "get_actionable_items",
        "notifications",
        ["--owner", "o", "--repo", "r", "--output-format", "json"],
        [
            make_completed_process(stdout="me\n"),   # _get_current_user
            make_completed_process(stdout="[]"),     # _try_notifications
            make_completed_process(stdout="[]"),     # _get_review_requests
            make_completed_process(stdout="[]"),     # _get_authored_prs
            make_completed_process(stdout="[]"),     # _get_assigned_issues
        ],
    ),
]

# pr/ residual: tracked by issue #2388, converted in a follow-up.
PR_RESIDUAL = [
    "add_pr_review_thread_reply",
    "close_pr",
    "detect_copilot_followup_pr",
    "detect_stale_pr_comments",
    "get_pr_comments_by_reviewer",
    "get_pr_review_comments",
    "get_pr_review_threads",
    "get_pr_reviewers",
    "get_thread_by_id",
    "get_thread_conversation_history",
    "get_unresolved_review_threads",
    "invoke_pr_comment_processing",
    "merge_pr",
    "new_pr",
    "post_pr_comment_reply",
    "resolve_pr_review_thread",
    "run_completion_gate",
    "set_pr_auto_merge",
    "test_pr_merged",
    "test_pr_merge_ready",
    "unresolve_pr_review_thread",
    "validate_pr_description",
    "wait_for_unresolved_zero",
]


@pytest.mark.parametrize(
    ("name", "subdir", "argv", "side_effects"),
    CONVERTED_SCRIPTS,
    ids=[row[0] for row in CONVERTED_SCRIPTS],
)
def test_script_emits_canonical_envelope(
    name, subdir, argv, side_effects, capsys, _restore_modules,
):
    mod = import_skill_script(name, subdir)

    with (
        patch.object(mod, "assert_gh_authenticated", create=True),
        patch.object(
            mod, "resolve_repo_params", return_value=RepoInfo(owner="o", repo="r"),
            create=True,
        ),
        patch("subprocess.run", side_effect=side_effects),
    ):
        rc = mod.main(argv)

    assert rc == 0
    envelope = _last_json_object(capsys.readouterr().out)
    assert set(envelope.keys()) == CANONICAL_KEYS, (
        f"{name} emitted top-level keys {sorted(envelope.keys())}, "
        f"expected {sorted(CANONICAL_KEYS)}"
    )
    assert envelope["Success"] is True
    assert envelope["Error"] is None
    assert set(envelope["Metadata"].keys()) == {"Script", "Version", "Timestamp"}


def test_pr_residual_is_tracked():
    """The pr/ residual list is non-empty and references issue #2388.

    This is a placeholder guard: when a pr/ script is converted, remove it from
    PR_RESIDUAL and add it to CONVERTED_SCRIPTS. The test fails loudly if the
    list is emptied without the parametrized table growing, preventing silent
    drift of the residual.
    """
    assert PR_RESIDUAL, "PR_RESIDUAL emptied: move converted pr/ scripts to CONVERTED_SCRIPTS"
