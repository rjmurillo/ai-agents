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
