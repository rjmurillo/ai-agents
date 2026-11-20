"""The same-PR replay runner rejects option-shaped git arguments."""

import json

import pytest

from scripts.eval import docs_review_same_pr_replay as replay


def test_replay_rejects_option_shaped_inputs() -> None:
    with pytest.raises(ValueError, match="revision"):
        replay.git_sha("--upload-pack=evil")
    with pytest.raises(ValueError, match="pull request"):
        replay.pr_number("1;rm")
    with pytest.raises(ValueError, match="ref token"):
        replay.ref_token("owned/../x")
    with pytest.raises(ValueError, match="case id"):
        replay.case_id("--output")


def test_committed_corpus_ids_fit_the_replay_tokens() -> None:
    corpus = json.loads(replay.CORPUS.read_text(encoding="utf-8"))

    for case in corpus["cases"]:
        replay.case_id(case["id"])
        replay.pr_number(case["pr"])
        if case.get("sha"):
            replay.git_sha(case["sha"])


def test_checklist_covers_expected_paths_and_bare_names() -> None:
    """Expected files match a full path or a final path segment, not a substring."""
    entries = [
        {"prose_file": "scripts/validation/detect_adr_changes.py"},
        {"prose_file": "templates/skills/push-pr.SKILL.md.tmpl"},
    ]
    assert replay.checklist_covers(
        ["detect_adr_changes.py", "templates/skills/push-pr.SKILL.md.tmpl"],
        entries,
    )
    assert replay.checklist_covers(None, entries)
    assert not replay.checklist_covers(["changes.py"], entries)
    assert not replay.checklist_covers(["missing.md"], entries)


def test_receipt_fails_when_an_expected_checklist_file_is_absent() -> None:
    """Catch rate alone does not pass a receipt that dropped a checklist file."""
    rows = [
        {
            "scope": "automatic",
            "caught": [True],
            "findings_count": 1,
            "checklist_covers": True,
        },
        {
            "scope": "negative",
            "caught": [],
            "findings_count": 0,
            "checklist_covers": True,
        },
        {
            "scope": "manual",
            "caught": [],
            "findings_count": 0,
            "checklist_covers": False,
        },
    ]
    assert replay.run_passed(rows) is False
    rows[2]["checklist_covers"] = True
    assert replay.run_passed(rows) is True
