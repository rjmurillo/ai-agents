"""Tests for adr_reason: stated reasons, ranking and shape, markup stripping.

Cases port tests/reason-extract.test.ts of align-cli (MIT, Copyright (c) 2026 Align Tech
Ltd, see LICENSE-align): same inputs, same expected outputs, titles follow upstream. A
wrong "reason" is worse than none, so every shape that is not a reason must give None.
"""

from __future__ import annotations

import time

import pytest
from adr_reason import extract_reason
from reason_helpers import full

# ---------------------------------------------------------------------------
# stated reasons
# ---------------------------------------------------------------------------


def test_keeps_a_because_sentence_verbatim() -> None:
    body = "The old parser buffered the whole body because it predates streams."
    assert extract_reason("fix: parser", body) == body


def test_keeps_a_so_that_sentence() -> None:
    body = "Use a Map so that lookups stay constant time."
    assert extract_reason("feat: use Map", body) == body


def test_keeps_a_to_avoid_sentence_and_a_to_prevent_sentence() -> None:
    avoid = "Copy the buffer to avoid mutating the caller input."
    prevent = "Lock the file to prevent two writers racing each other."
    assert extract_reason("x", avoid) == avoid
    assert extract_reason("x", prevent) == prevent


def test_keeps_a_due_to_and_an_instead_of_sentence() -> None:
    due = extract_reason("x", "Dropped the retry loop due to unbounded memory growth in long runs.")
    assert due is not None
    assert "due to unbounded memory growth" in due
    instead = extract_reason(
        "x",
        "Use the native URL class instead of the hand rolled splitter, which broke on IPv6 hosts.",
    )
    assert instead is not None
    assert "instead of the hand rolled splitter" in instead


@pytest.mark.parametrize(
    "body",
    [
        "Use the native URL class instead of the hand rolled splitter here.",
        "The log no longer emits a redundant level change event per request.",
        "It was previously stored in a map and now lives in a plain object.",
        "The new options object replaces the older positional arguments entirely.",
    ],
)
def test_change_describing_words_alone_are_not_a_reason(body: str) -> None:
    assert extract_reason("x", body) is None


def test_the_same_words_next_to_a_named_problem_are_a_reason() -> None:
    crash = extract_reason("x", "Previously the worker would crash when the queue was empty.")
    leak = extract_reason("x", "Sockets are no longer left open, which was a leak under load.")
    assert crash is not None
    assert "would crash" in crash
    assert leak is not None
    assert "leak" in leak


def test_a_breaking_change_footer_describes_the_change_it_is_not_a_reason() -> None:
    body = "BREAKING CHANGE: define option no longer calls JSON.stringify on string values."
    assert extract_reason("x", body) is None


@pytest.mark.parametrize(
    "body",
    [
        "This function has been deprecated since node 16 in the docs.",
        "The frozen path has used the cache since pnpm/pnpm#14861 landed.",
        "It was a stable option since the first release of the package.",
    ],
)
def test_since_as_a_date_or_version_is_not_a_cause(body: str) -> None:
    assert extract_reason("x", body) is None


def test_since_before_a_clause_is_a_cause_with_a_noun_or_a_pronoun_as_its_subject() -> None:
    noun = extract_reason(
        "x", "The tool runs with the toolchain set, since Cargo finds subcommands in the bin dir."
    )
    pronoun = extract_reason("x", "Remove the plugin since it is no longer maintained by anyone.")
    assert noun is not None
    assert "since Cargo finds" in noun
    assert pronoun is not None
    assert "since it is" in pronoun


def test_a_reason_or_why_label_counts_as_a_marker_and_the_label_is_dropped() -> None:
    assert (
        extract_reason("x", "Reason: the cache grew without bound under load.")
        == "the cache grew without bound under load."
    )
    assert (
        extract_reason("x", "**Why:** callbacks hide errors from the async stack trace.")
        == "callbacks hide errors from the async stack trace."
    )


def test_since_as_a_cause_counts_since_v1_2_as_a_version_does_not() -> None:
    cause = extract_reason("x", "Since the lock was global, writers starved under load.")
    assert cause is not None
    assert "writers starved" in cause
    assert extract_reason("x", "Available since v1.2.0 of the router package.") is None


# ---------------------------------------------------------------------------
# ranking and shape
# ---------------------------------------------------------------------------


def test_returns_at_most_2_sentences_the_strongest_two_in_body_order() -> None:
    body = " ".join(
        [
            "Previously the worker would crash when the queue was empty.",
            "We switched because the old API leaked sockets under heavy load.",
            "It also helps in order to keep the surface area small for users.",
        ]
    )
    assert extract_reason("x", body) == (
        "We switched because the old API leaked sockets under heavy load. "
        "It also helps in order to keep the surface area small for users."
    )


def test_with_four_equally_strong_sentences_it_keeps_the_first_two() -> None:
    body = " ".join(
        [
            "One was done because reason alpha applies.",
            "Two was done because reason bravo applies.",
            "Three was done because reason charlie applies.",
            "Four was done because reason delta applies.",
        ]
    )
    assert extract_reason("x", body) == (
        "One was done because reason alpha applies. Two was done because reason bravo applies."
    )


def test_caps_each_sentence_near_180_chars_at_a_word_boundary() -> None:
    out = extract_reason("x", f"We changed it because {'reallylongword ' * 30}end.")
    assert out is not None
    assert len(out) <= 183
    assert out.endswith("...")
    assert not out.endswith("reallylongwor...")


def test_a_sentence_longer_than_the_cap_whose_marker_is_past_the_cut_is_dropped() -> None:
    lead = (
        "The configuration loader reads every file in the project directory and then merges "
        "them in order"
    )
    filler = "with some more words about it " * 3
    body = f"{lead} {filler}, because the cache grew without bound under load."
    assert extract_reason("x", body) is None


def test_a_long_sentence_whose_marker_is_inside_the_cap_is_kept_and_cut_at_a_word() -> None:
    out = extract_reason("x", f"We did it because the cache grew {'and grew ' * 40}forever.")
    assert out is not None
    assert out.startswith("We did it because the cache grew")
    assert out.endswith("...")


def test_a_long_sentence_with_no_commas_and_a_late_marker_is_dropped_too() -> None:
    assert extract_reason("x", f"{'word ' * 60}because x.") is None


def test_a_labelled_reason_longer_than_the_cap_is_cut_not_dropped() -> None:
    out = extract_reason("x", f"Reason: {'the cache grew ' * 30}because forever.")
    assert out is not None
    assert out.startswith("the cache grew")
    assert out.endswith("...")


def test_a_quoted_line_is_read_without_its_quote_marker() -> None:
    body = "> We removed it because it was slow on every request."
    assert extract_reason("x", body) == "We removed it because it was slow on every request."


def test_joins_hard_wrapped_lines_of_one_paragraph() -> None:
    body = "We removed it because\nit was slow on every\nrequest we measured."
    assert (
        extract_reason("x", body)
        == "We removed it because it was slow on every request we measured."
    )


def test_handles_crlf_line_endings_with_no_stray_carriage_returns() -> None:
    body = (
        "We removed it because\r\nit was slow on every\r\nrequest we measured."
        "\r\n\r\nSigned-off-by: A <a@b.c>\r\n"
    )
    out = extract_reason("x", body)
    assert out == "We removed it because it was slow on every request we measured."
    assert out is not None
    assert "\r" not in out


def test_crlf_in_a_whole_importer_summary_still_strips_the_metadata_block() -> None:
    crlf = full("fix: parser", "We removed it because the old one leaked.").replace("\n", "\r\n")
    assert extract_reason("fix: parser", crlf) == "We removed it because the old one leaked."


def test_a_very_long_single_line_is_bounded_and_still_finds_an_early_reason() -> None:
    body = f"We did this because the old path leaked sockets. {'Filler words. ' * 20000}"
    started = time.perf_counter()
    out = extract_reason("x", body)
    assert time.perf_counter() - started < 0.5
    assert out == "We did this because the old path leaked sockets."


def test_reads_only_the_head_of_a_body_a_reason_past_the_cap_is_not_found() -> None:
    filler = "Filler words. " * 600
    assert extract_reason("x", f"{filler}We did this because of a leak.") is None
    assert (
        extract_reason("x", f"We did this because of a leak. {filler}")
        == "We did this because of a leak."
    )


def test_is_deterministic() -> None:
    body = "We did it because it was slow. Also to avoid a crash on empty input."
    assert extract_reason("t", body) == extract_reason("t", body)


# ---------------------------------------------------------------------------
# markup is stripped, never quoted
# ---------------------------------------------------------------------------


def test_strips_emphasis_code_ticks_and_link_syntax() -> None:
    body = "We need this because `foo` is [deprecated](https://x.test/z) in **v3**."
    assert extract_reason("x", body) == "We need this because foo is deprecated in v3."


def test_removes_bare_urls_and_leaves_no_gap_before_punctuation() -> None:
    body = (
        "We moved because the limit was hit, see "
        "https://example.com/very/long/path/that/goes/on/forever for details."
    )
    assert extract_reason("x", body) == "We moved because the limit was hit, see for details."


def test_a_reason_whose_object_was_a_url_is_dropped_not_printed_with_a_hole_in_it() -> None:
    first = (
        "this was not working because of https://github.com/o/r/pull/1#discussion_r2 "
        "and https://github.com/o/r/pull/3"
    )
    assert extract_reason("x", first) is None
    assert (
        extract_reason("x", "We reverted due to https://example.com/incident-4 and the rollback.")
        is None
    )


def test_strips_real_html_tags_but_keeps_their_text() -> None:
    body = 'We dropped <b>it</b> because the <a href="https://x.test">parser</a> was slow.'
    assert extract_reason("x", body) == "We dropped it because the parser was slow."


def test_a_space_before_a_dotted_name_is_kept() -> None:
    body = "We read the .env file because the .npmrc layer is ignored by call .bind(reply) here."
    assert extract_reason("x", body) == body


def test_placeholder_text_in_angle_brackets_is_not_html_and_survives() -> None:
    body = "Run with <path> set because the default dir is read only."
    assert extract_reason("x", body) == body


def test_drops_html_comments_alone_or_around_a_real_sentence() -> None:
    assert extract_reason("x", "<!-- because this is a template hint -->") is None
    body = "<!-- template\nbecause hint -->\nWe dropped it because it was unsafe to keep."
    assert extract_reason("x", body) == "We dropped it because it was unsafe to keep."


def test_ignores_fenced_code() -> None:
    fenced = "```js\n// because we need to avoid the slow path here\nrun();\n```"
    assert extract_reason("x", fenced) is None
    tilde = "Before.\n\n~~~\nbecause we need to avoid the slow path here\n~~~"
    assert extract_reason("x", tilde) is None
