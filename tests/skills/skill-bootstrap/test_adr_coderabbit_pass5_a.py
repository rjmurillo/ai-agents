"""CodeRabbit pass 5, group A: titles, trailers, fences, comments, quotes and cut reasons."""

from __future__ import annotations

import time

import adr_reason
import adr_shape
import pytest

F3 = "`" * 3
LIMIT_S = 1.0


def _reason(body: str, title: str = "Adopt X for parsing") -> str | None:
    reason: str | None = adr_reason.extract_reason(title, body)
    return reason


def _rationale(body: str, subject: str = "Use a queue for background jobs") -> bool:
    return adr_shape.has_stated_rationale(subject, body)


# A1: a release title with a decision after its version reaches the rationale gate


def test_a_release_title_that_states_a_policy_is_a_decision() -> None:
    subject = "Release 2.4 under the canary policy"

    assert not adr_shape.is_release_or_bump_subject(subject)
    assert adr_shape.is_decision_commit(subject)


@pytest.mark.parametrize(
    "subject", ["Release 2.4", "Release v2.4.0-rc.1", "Released 5.11.2 with the fixes below"]
)
def test_a_version_only_or_plain_release_title_stays_housekeeping(subject: str) -> None:
    assert adr_shape.is_release_or_bump_subject(subject)


# A2: a reason hard-wrapped after its causal marker stays one unit


def test_a_reason_wrapped_after_because_is_joined() -> None:
    body = "We chose this design because\nPostgreSQL handles the load without replicas."

    assert _reason(body) == (
        "We chose this design because PostgreSQL handles the load without replicas."
    )


def test_short_list_items_still_split() -> None:
    body = "Fast startup\nLow memory use on small hosts\nWe keep it because the old one leaked."

    assert _reason(body) == "We keep it because the old one leaked."


# A3: an unindented footer continuation line before BREAKING CHANGE


def test_an_unindented_footer_value_line_does_not_hide_a_breaking_footer() -> None:
    body = (
        "Body.\n\nNotes: The rollout has two phases.\nThe second phase starts in June.\n"
        "BREAKING CHANGE: Remove the legacy wire format."
    )

    assert adr_reason.breaking_change("feat: new wire format", body)


@pytest.mark.parametrize(
    "paragraph",
    [
        "Some prose first.\nBREAKING CHANGE: Remove the legacy wire format.",
        "The rollout has two phases.\nNotes: x\nBREAKING CHANGE: Remove the legacy wire format.",
    ],
)
def test_a_breaking_paragraph_must_open_with_a_footer(paragraph: str) -> None:
    assert not adr_reason.breaking_change("feat: new wire format", f"Body.\n\n{paragraph}")


# A4: a Change-Id trailer is not a rationale, an Issue sentence still is


@pytest.mark.parametrize(
    "body", ["Change-Id: I1234", "Reviewed-on: https://r.example/c/1", "Issue: #123"]
)
def test_a_known_trailer_is_not_a_rationale(body: str) -> None:
    assert not _rationale(body, "feat: Switch to a shared worker queue")


def test_an_issue_line_that_explains_the_problem_is_a_rationale() -> None:
    assert _rationale("Issue: users get a 500 when the token expires", "feat: Switch queues")


# A5: mechanical prefixes match whole words only


@pytest.mark.parametrize(
    "subject",
    ["Mergeable queues must preserve arrival order", "Choreography must preserve event order"],
)
def test_a_word_that_starts_with_a_mechanical_prefix_is_a_decision(subject: str) -> None:
    assert adr_shape.is_decision_commit(subject)


@pytest.mark.parametrize(
    "subject",
    ["Merge pull request #12 from o/branch", "chore: tidy the whole thing up now", "wip"],
)
def test_a_mechanical_prefix_word_is_still_mechanical(subject: str) -> None:
    pattern = adr_shape.mechanical_subject_regex(adr_shape.MECHANICAL_SUBJECT_PREFIXES)

    assert pattern.search(subject)


def test_a_punctuation_prefix_still_matches_before_a_colon() -> None:
    assert adr_shape.mechanical_subject_regex(["c++"]).search("c++: rebuild the parser")


# A6: inline code is not the author's rationale


def test_a_because_inside_inline_code_does_not_score() -> None:
    assert _reason("The sample prints `because old clients ignore the header`.") is None


def test_a_because_in_prose_around_inline_code_still_scores() -> None:
    body = "We set `X-Mode` on every call because old clients ignore the header."

    assert _reason(body) == "We set X-Mode on every call because old clients ignore the header."


def test_a_sentence_break_inside_inline_code_does_not_leak_a_reason() -> None:
    assert _reason("The sample prints `Done. Because old clients ignore it, we retry.`") is None


def test_a_because_inside_double_backtick_code_does_not_score() -> None:
    assert _reason("The sample prints ``because old clients ignore the header``.") is None


def test_a_url_in_inline_code_does_not_swallow_the_closing_backtick() -> None:
    body = "We call `https://x.example/api` because the `v1` path drops writes under load."

    assert _reason(body) == "We call because the v1 path drops writes under load."


# A7: an empty heading does not swallow the next line as a release heading


def test_an_empty_heading_does_not_turn_the_next_line_into_a_release_heading() -> None:
    reason = "1.2 is the minimum version because older readers cannot decode these headers."

    assert _reason(f"# \n{reason}", "Raise the minimum reader version") == reason


def test_a_same_line_release_heading_still_stops_extraction() -> None:
    body = "## 1.2\n\nWe moved because older readers cannot decode these headers."

    assert _reason(body, "Raise the minimum reader version") is None


# A8: Unicode padding after a fence mark is not a closer


def test_a_nbsp_after_a_fence_mark_does_not_close_the_fence() -> None:
    body = f"Body.\n\n{F3}\n{F3} \nBREAKING CHANGE: sample only\n{F3}"

    assert not adr_reason.breaking_change("feat: x", body)


# A9: fenced examples inside a blockquote


QUOTED = f"> {F3}\n> We retry because the API drops bursts of calls.\n> {F3}"


def test_a_quoted_fence_is_not_a_rationale() -> None:
    assert not _rationale(QUOTED)
    assert _reason(QUOTED) is None


def test_quoted_prose_around_a_quoted_fence_still_counts() -> None:
    body = f"> We use a queue because the API drops bursts.\n{QUOTED}"

    assert _reason(body) == "We use a queue because the API drops bursts."


def test_an_unclosed_quoted_fence_ends_with_its_blockquote() -> None:
    body = f"> {F3}\n> example because code\n\nWe use a queue because the API drops bursts."

    assert _reason(body) == "We use a queue because the API drops bursts."


# A10: a cut reason must keep part of its cause


def test_a_cut_that_leaves_only_the_marker_is_dropped() -> None:
    assert _reason("word " * 34 + "because replicas lose writes.") is None


def test_a_cut_that_keeps_part_of_the_cause_is_shown() -> None:
    body = "word " * 30 + "because replicas lose writes when the primary fails over twice in a row."

    reason = _reason(body)

    assert reason is not None and reason.endswith("because replicas lose writes...")


def test_a_reason_that_fits_is_kept_whole() -> None:
    body = "word " * 20 + "because replicas lose writes."

    assert _reason(body) == body.strip()


# A11: an unclosed fence is code to the end of the body (CommonMark 0.31.2)


def test_an_unclosed_tilde_fence_hides_a_breaking_footer() -> None:
    body = "~~~text\n\nBREAKING CHANGE: The old API is removed."

    assert not adr_reason.breaking_change("feat: x", body)


@pytest.mark.parametrize(
    ("subject", "body"),
    [
        ("feat: x", "Body.\n\nBREAKING CHANGE: The old API is removed."),
        ("feat!: x", f"{F3}\nunclosed"),
    ],
)
def test_an_unfenced_footer_and_a_bang_subject_stay_breaking(subject: str, body: str) -> None:
    assert adr_reason.breaking_change(subject, body)


# A12: text inside a quotation is not the author's rationale


def test_a_quoted_sentence_break_does_not_leak_a_reason() -> None:
    body = 'The guide says "Do not retry. Because retries overload the node during recovery."'

    assert _reason(body) is None


@pytest.mark.parametrize(
    "body",
    [
        'Set the panel to 12" wide. We keep it because the old layout broke on phones.',
        'The "legacy mode is gone. We keep it because the old layout broke on phones.',
    ],
)
def test_a_reason_after_an_unmatched_quote_mark_still_qualifies(body: str) -> None:
    assert _reason(body) == "We keep it because the old layout broke on phones."


def test_a_reason_with_a_quoted_word_after_a_stray_inch_mark_qualifies() -> None:
    body = 'The 12" panel ships today. We chose it because "retina" screens cost more.'

    assert _reason(body) == 'We chose it because "retina" screens cost more.'


# A13: a fence marker indented four columns is not a fence


REASON = "We use a queue because bursts overload the API."


@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_an_indented_marker_does_not_open_a_fence(indent: str) -> None:
    body = f"{indent}{F3}\n\n{REASON}"

    assert _rationale(body)
    assert _reason(body) == REASON


@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_an_indented_marker_line_alone_is_not_a_rationale(indent: str) -> None:
    assert not _rationale(f"{indent}{F3}")


@pytest.mark.parametrize("mark", [F3, "~~~"])
def test_an_indented_marker_line_is_never_part_of_the_extracted_reason(mark: str) -> None:
    body = f"    {mark}\nretry because the API drops bursts of calls\n    {mark}"

    # No indented-code rule exists, so the inner line is prose; the marker lines are not.
    assert _reason(body) == "retry because the API drops bursts of calls"


def test_an_indented_marker_inside_a_fence_does_not_close_it() -> None:
    body = f"{F3}\nold = 1\n    {F3}\nnew = 2 because it is faster\n{F3}"

    assert not _rationale(body)
    assert _reason(body) is None


@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_an_indented_marker_inside_a_fence_does_not_close_it_for_breaking(indent: str) -> None:
    body = f"Body.\n\n{F3}\n{indent}{F3}\nBREAKING CHANGE: sample only\n{F3}"

    assert not adr_reason.breaking_change("feat: x", body)


# A14: HTML comments are template text, not a rationale


def test_a_template_comment_is_not_a_rationale() -> None:
    assert not _rationale("<!-- Describe why this change is needed. -->", "Use SQLite for storage")


def test_prose_after_a_closed_comment_still_counts() -> None:
    assert _rationale("<!-- template -->\nWe use SQLite because the client runs offline.")


@pytest.mark.parametrize(
    "body",
    [
        f"<!-- {F3} -->\nWe use SQLite because the client runs offline.",
        f"{F3}\n<!--\n{F3}\nWe use SQLite because the client runs offline.",
    ],
)
def test_a_fence_and_a_comment_do_not_hide_prose_outside_them(body: str) -> None:
    assert _rationale(body)


# Every new or changed pattern stays linear on 64 KiB of hostile input


_K = 64 * 1024
_HOSTILE = {
    "quoted openers": f"> {F3}\n" * (_K // 6),
    "quoted near closers": f"> {F3}\n" + f"> {F3} x\n" * (_K // 8),
    "quote marks": ">" * _K,
    "spaces after a quote": ">" + " " * _K + "x",
    "indented markers": f"    {F3}\n" * (_K // 8),
    "release tail": "Release 1.2 " + "word " * (_K // 5),
    "release version": "Release 1." + "1." * (_K // 2) + "x y",
    "prefix word": "merge" + "a" * _K,
    "breaking footers": "Notes: x\n" + "plain line\n" * (_K // 11) + "BREAKING CHANGE: y",
    "quotes": '"a. B ' * (_K // 6),
    "inline code": "`a` " * (_K // 4),
    "becauses": "because " * (_K // 8),
    "empty headings": "# \n" * (_K // 3),
}


@pytest.mark.parametrize("text", _HOSTILE.values(), ids=_HOSTILE.keys())
def test_the_pass5_patterns_are_linear_on_hostile_input(text: str) -> None:
    start = time.perf_counter()

    adr_shape.CODE_BLOCK.sub("\n", text)
    adr_shape.has_stated_rationale("feat: Switch to bounded queues", text)
    adr_shape.is_decision_commit(text)
    adr_reason.breaking_change("feat: x", text)
    adr_reason.extract_reason("Adopt X", text)

    assert time.perf_counter() - start < LIMIT_S


# A-echo: a long title restated with a short reason after it keeps the reason

LONG_TITLE = (
    "Use SQLite as the primary local database for mobile clients operating in environments"
    " where network connections are unreliable or unavailable"
)


def test_a_long_title_restated_with_a_short_reason_keeps_the_reason() -> None:
    body = f"{LONG_TITLE} because access fails often."

    assert _reason(body, LONG_TITLE) == body


def test_a_long_title_restated_alone_is_still_an_echo() -> None:
    assert _reason(f"{LONG_TITLE}.", LONG_TITLE) is None


def test_a_title_that_already_says_because_is_an_echo_when_restated() -> None:
    title = "Use SQLite for local storage because devices often lose network access"

    assert _reason(f"{title}.", title) is None
