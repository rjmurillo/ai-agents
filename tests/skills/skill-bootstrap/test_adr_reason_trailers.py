"""Tests for adr_reason and adr_trailers: trailers, strip_trailers, commit_sha_of, port fixes.

Cases port tests/reason-extract.test.ts of align-cli (MIT, Copyright (c) 2026 Align Tech
Ltd, see LICENSE-align): same inputs, same expected outputs, titles follow upstream. A
wrong "reason" is worse than none, so every shape that is not a reason must give None.
"""

from __future__ import annotations

import adr_reason
import pytest
from adr_reason import extract_reason
from adr_trailers import strip_trailers
from reason_helpers import SHA, full

# ---------------------------------------------------------------------------
# commit trailers are never part of the stated reason
# ---------------------------------------------------------------------------

SUBJECT = "fix(pool): cap the worker pool"
SESSION = "Claude-Session: https://claude.ai/code/session_01ABC"


def test_drops_a_trailer_right_under_the_reason_line_with_no_blank_line_and_an_unlisted_key() -> (
    None
):
    reason = (
        "We cap the pool at 12 because the gateway rejects more than twelve concurrent "
        "calls from one token"
    )
    assert extract_reason(SUBJECT, full(SUBJECT, f"{reason}\n{SESSION}")) == reason


def test_does_not_read_a_trailer_as_the_reason_because_its_value_holds_a_marker_word() -> None:
    body = (
        "Cap the pool.\n\nChange-Reason: because the gateway rejects more than 12 concurrent "
        f"calls today\n{SESSION}"
    )
    assert extract_reason(SUBJECT, full(SUBJECT, body)) is None


def test_leaves_the_reason_paragraph_above_a_blank_line_and_a_trailer_block_as_it_was() -> None:
    body = (
        "We cap the pool because the gateway rejects bigger ones.\n\n"
        f"Co-Authored-By: X <x@y.test>\n{SESSION}\nSigned-off-by: T <t@e.test>"
    )
    assert (
        extract_reason(SUBJECT, full(SUBJECT, body))
        == "We cap the pool because the gateway rejects bigger ones."
    )


def test_still_reads_a_labelled_reason_and_a_closing_note_both_are_prose_not_provenance() -> None:
    labelled = full("fix: bound the cache", "Reason: the cache grew without bound under load.")
    assert (
        extract_reason("fix: bound the cache", labelled)
        == "the cache grew without bound under load."
    )
    note = "Note: this keeps the default at 12 because the gateway rejects more than that."
    assert extract_reason(SUBJECT, full(SUBJECT, f"Sizing was hard-coded.\n\n{note}")) == note


def test_applies_the_rule_to_a_stored_commit_only_a_pr_body_keeps_its_closing_key_value_line() -> (
    None
):
    body = (
        "Sizing was hard-coded.\n\n"
        "Result: the import is three times faster because syncs are batched."
    )
    expected = "Result: the import is three times faster because syncs are batched."
    assert extract_reason("Batch the syncs", body) == expected
    assert extract_reason("Batch the syncs", full("Batch the syncs", body)) is None


# ---------------------------------------------------------------------------
# strip_trailers
# ---------------------------------------------------------------------------


def test_strip_trailers_removes_the_run_that_ends_the_last_paragraph_and_the_blank_line_above() -> (
    None
):
    block = (
        "Co-Authored-By: X <x@y.test>\nClaude-Session: https://claude.ai/code/session_01ABC\n"
        "Signed-off-by: T <t@e.test>"
    )
    assert strip_trailers(f"Why we did it.\n\n{block}") == "Why we did it."
    assert strip_trailers(f"Why we did it.\n\n{block}\n\n") == "Why we did it."
    assert strip_trailers("First.\n\nSecond.\n\nRefs: PROJ-12\nCloses: #45") == "First.\n\nSecond."
    assert (
        strip_trailers("A long reason line with no full stop\nClaude-Session: https://x.test/s")
        == "A long reason line with no full stop"
    )
    assert strip_trailers("Claude-Session: https://x.test/s") == ""


def test_strip_trailers_leaves_a_line_in_an_earlier_paragraph_or_with_a_prose_line_under_it() -> (
    None
):
    earlier = "Intro.\n\nCc: a mid-body note\n\nMore text."
    assert strip_trailers(earlier) == earlier
    prose_under = (
        "It changes two things. The pool size, and\nSecond: the timeout, which was never read\n"
        "by the gateway at all."
    )
    assert strip_trailers(prose_under) == prose_under
    assert strip_trailers(f"{earlier}\n\nSigned-off-by: A <a@b.test>") == earlier


@pytest.mark.parametrize(
    "label", ["Why", "Reason", "Rationale", "Motivation", "Note", "note", "REASON"]
)
def test_strip_trailers_never_treats_a_prose_label_as_a_trailer(label: str) -> None:
    text = f"Changed the cap.\n\n{label}: the gateway rejects bigger pools."
    assert strip_trailers(text) == text


def test_strip_trailers_a_prose_label_survives_above_a_real_trailer() -> None:
    text = (
        "Changed the cap.\n\nNote: the gateway rejects bigger pools.\nSigned-off-by: A <a@b.test>"
    )
    assert strip_trailers(text) == "Changed the cap.\n\nNote: the gateway rejects bigger pools."


def test_strip_trailers_reads_issue_and_bug_as_trailers_only_when_the_value_is_a_reference() -> (
    None
):
    assert strip_trailers("Issue: users get a 500 when the token expires") == (
        "Issue: users get a 500 when the token expires"
    )
    assert strip_trailers("Fixed the guard.\n\nBug: crash on empty input") == (
        "Fixed the guard.\n\nBug: crash on empty input"
    )
    assert strip_trailers("Fixed the guard.\n\nIssue: #123") == "Fixed the guard."
    assert (
        strip_trailers("Fixed the guard.\n\nBug: PROJ-12, #4 and https://x.test/issues/9.")
        == "Fixed the guard."
    )
    assert strip_trailers("Fixed the guard.\n\nBug: 1234567") == "Fixed the guard."


def test_strip_trailers_keeps_a_line_in_conventional_commit_form() -> None:
    last = "Squashed.\n\nfix: retry on 503 because the gateway drops idle sockets"
    assert strip_trailers(last) == last
    scoped = "Squashed.\n\nfeat(pool)!: size the pool from config"
    assert strip_trailers(scoped) == scoped
    assert (
        strip_trailers("Squashed.\n\nfix: retry on 503\nSigned-off-by: A <a@b.test>")
        == "Squashed.\n\nfix: retry on 503"
    )


@pytest.mark.parametrize(
    "text",
    [
        "See the report.\n\nhttps://example.test/only-a-url",
        "The deadline is\n12:30 sharp",
        "We changed two things: the cap and the timeout",
        "Breaking change: the cap is now 12",
    ],
)
def test_strip_trailers_needs_a_one_token_key_and_a_space_after_the_colon(text: str) -> None:
    assert strip_trailers(text) == text


def test_strip_trailers_keeps_an_indented_block_four_spaces_is_a_code_example() -> None:
    text = "Set the headers in the proxy:\n\n    Cache-Control: no-store\n    X-Pool-Size: 12"
    assert strip_trailers(text) == text
    assert strip_trailers("Why we did it.\n\n  Signed-off-by: A <a@b.test>") == "Why we did it."


@pytest.mark.parametrize(
    "text",
    ["", "Just prose here.", "First.\n\nSecond paragraph, because of a reason.\n", "  \n\n "],
)
def test_strip_trailers_returns_the_same_string_when_there_is_no_trailer(text: str) -> None:
    assert strip_trailers(text) == text


def test_strip_trailers_never_strips_the_commit_subject_whatever_its_shape() -> None:
    subject = "Release: cut the 1.2 line"
    assert strip_trailers(f"{subject}\nSigned-off-by: A <a@b.test>", subject) == subject
    assert strip_trailers(subject, subject) == subject
    assert strip_trailers(f"{subject}\n\nSigned-off-by: A <a@b.test>", subject) == subject


# ---------------------------------------------------------------------------
# commit_sha_of (not covered by upstream tests)
# ---------------------------------------------------------------------------


def test_commit_sha_of_reads_the_sha_from_a_commit_url_or_the_git_scheme() -> None:
    assert adr_reason.commit_sha_of(f"https://github.com/o/r/commit/{SHA}") == SHA
    assert adr_reason.commit_sha_of("https://github.com/o/r/commit/abc1234?x=1") == "abc1234"
    assert adr_reason.commit_sha_of("git://commit/abc1234") == "abc1234"


@pytest.mark.parametrize(
    "url", [None, "", "https://github.com/o/r/pull/12", "https://github.com/o/r/commit/abc12"]
)
def test_commit_sha_of_is_none_for_anything_else(url: str | None) -> None:
    assert adr_reason.commit_sha_of(url) is None


# ---------------------------------------------------------------------------
# defects fixed in the port: guards against a naive Python translation of the source
# ---------------------------------------------------------------------------


def test_letter_ratio_counts_non_ascii_letters_as_letters() -> None:
    # An ASCII-only letter count sees 100 percent English here and keeps the sentence.
    russian = (
        "Мы удалили стары"
        "й разборщик пото"
        "му что он был медл"
        "енный because slow on every request we measured."
    )
    assert extract_reason("x", russian) is None


def test_letter_ratio_keeps_a_mostly_english_sentence_with_a_few_accented_letters() -> None:
    body = "We removed the café parser because it was slow on every request."
    assert extract_reason("x", body) == body


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "We pinned the cache, e.g. Redis 7, because the old one leaked sockets. It was slow.",
            "We pinned the cache, e.g. Redis 7, because the old one leaked sockets.",
        ),
        (
            "We dropped the shim, i.e. The Old One, because it leaked memory under load.",
            "We dropped the shim, i.e. The Old One, because it leaked memory under load.",
        ),
        (
            "We chose streams vs. Buffers because the buffers leaked memory under load.",
            "We chose streams vs. Buffers because the buffers leaked memory under load.",
        ),
        (
            "Pin Python to 3.10.2 because 3.10.1 crashed on startup. Newer builds work.",
            "Pin Python to 3.10.2 because 3.10.1 crashed on startup.",
        ),
    ],
    ids=["e.g.", "i.e.", "vs.", "version number"],
)
def test_the_sentence_splitter_does_not_split_on_abbreviations_or_version_numbers(
    body: str, expected: str
) -> None:
    assert extract_reason("x", body) == expected


def test_the_sentence_splitter_still_splits_after_a_version_at_the_end_of_a_sentence() -> None:
    body = "Pin to 3.10. Then 3.11 crashed because of a regression bug in the parser."
    assert (
        extract_reason("x", body) == "Then 3.11 crashed because of a regression bug in the parser."
    )


def test_the_sentence_splitter_still_splits_after_a_word_that_ends_like_an_abbreviation() -> None:
    # "Dr." is an abbreviation, "nodr." is not: the abbreviation needs a word boundary.
    body = "We tightened the nodr. Then the parser crashed because the old path leaked sockets."
    assert (
        extract_reason("x", body) == "Then the parser crashed because the old path leaked sockets."
    )
