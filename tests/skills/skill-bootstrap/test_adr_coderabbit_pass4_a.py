"""CodeRabbit pass 4, group A: reason extraction, fences, titles, trailers and breaking footers."""

from __future__ import annotations

import itertools
import re
import time

import adr_reason
import adr_shape
import pytest

F3, F4 = "`" * 3, "`" * 4
LIMIT_S = 1.0
REASON = "We adopt X because the old parser leaked memory on large inputs."


def _reason(body: str, title: str = "Adopt X for parsing") -> str | None:
    reason: str | None = adr_reason.extract_reason(title, body)
    return reason


# Thread PRRT_kwDOQoWRls67QJRG: a body that opens with the title and then gives a reason


def test_a_body_that_extends_the_title_with_a_reason_is_kept() -> None:
    body = "Use SQLite for local storage because our devices often lose network access."

    assert _reason(body, "Use SQLite for local storage") == body


def test_a_cut_title_that_already_holds_the_reason_is_still_an_echo() -> None:
    title = "Use SQLite because devices go offline when the train enters"
    body = "Use SQLite because devices go offline when the train enters a tunnel under the hills."

    assert _reason(body, title) is None


# A1: ordinary "Updates to ..." prose is not a dependency bump


def test_updates_to_prose_is_not_a_bump_body() -> None:
    body = "Updates to the wire protocol are needed because retries can duplicate requests."

    assert _reason(body, "Change the wire protocol") == body


@pytest.mark.parametrize(
    "body",
    [
        "Update lodash from v4.17.20 to v4.17.21 because it fixes a leak.",
        "Upgrades `serde` to 1.0.200 because the old one leaked memory.",
        "Bumps [x](https://github.com/o/x) from 1.0.0 to 1.1.0 because it is faster.",
    ],
)
def test_a_dependency_moving_to_a_version_is_still_a_bump_body(body: str) -> None:
    assert _reason(body) is None


# A3: a code fence is not rationale


@pytest.mark.parametrize(
    "body",
    [
        f"{F3}python\nq = Queue(10)\n{F3}",
        "~~~\nq = Queue(10)\n~~~",
        f"{F3}\nq = Queue(10)",
        f"{F4}\n{F3}\nq = Queue(10)\n{F3}\n{F4}",
    ],
)
def test_a_body_of_only_code_states_no_reason(body: str) -> None:
    assert not adr_shape.has_stated_rationale("feat: Switch to bounded queues", body)


@pytest.mark.parametrize(
    "body",
    [
        f"{F3}\nq = Queue(10)\n{F3}\nUnbounded queues ran the host out of memory.",
        f"{F3}old{F3} is renamed to {F3}new{F3} so callers see one name.",
    ],
)
def test_prose_after_a_closed_fence_or_with_inline_code_still_counts(body: str) -> None:
    assert adr_shape.has_stated_rationale("feat: Switch to bounded queues", body)


# A4: a title that states a rule is decision-shaped


@pytest.mark.parametrize(
    "title", ["Do not force close sockets after a timeout", "feat: do not store raw tokens"]
)
def test_a_rule_stating_title_is_decision_shaped(title: str) -> None:
    assert adr_shape.is_decision_shaped_title(title)


@pytest.mark.parametrize(
    "title", ["docs: do not use the old flag", "fix: never retry a POST", "test: must not leak"]
)
def test_a_fix_shaped_type_still_drops_a_rule_title(title: str) -> None:
    assert not adr_shape.is_decision_shaped_title(title)


# A5: prose that opens with a heading word is not a release-note heading


def test_prose_starting_with_features_is_a_reason() -> None:
    body = "Features are disabled by default because embedded devices have limited memory."

    assert _reason(body, "Disable optional features by default") == body


@pytest.mark.parametrize(
    "heading",
    ["## Features", "### Bug Fixes", "Features", "Features:", "**Features**", "What's Changed"],
)
def test_a_real_heading_still_starts_a_dump(heading: str) -> None:
    body = f"{heading}\n\n- avoid the crash because the parser was incorrect upstream"

    assert _reason(body) is None


def test_a_bold_full_changelog_label_still_starts_a_dump() -> None:
    body = f"{REASON}\n\n**Full Changelog**: https://x.example/compare/a...b because of x"

    assert _reason(body) == REASON


# A6: a reference-only trailer is a trailer whatever the case of its key


@pytest.mark.parametrize("line", ["issue: #42", "Issue: #42", "bug: GH-7", "bug: #1, #2"])
def test_a_reference_only_issue_or_bug_line_is_a_trailer(line: str) -> None:
    assert adr_shape.is_trailer_line(line)


@pytest.mark.parametrize(
    "line", ["issue: users get a 500 when the token expires", "fix: retry on 503", "Why: speed"]
)
def test_prose_and_subject_lines_are_not_trailers(line: str) -> None:
    assert not adr_shape.is_trailer_line(line)


def test_a_lowercase_issue_trailer_is_stripped() -> None:
    assert adr_shape.strip_trailers("Body text.\n\nissue: #42") == "Body text."


# A7: a release policy title is not housekeeping


def test_a_release_policy_title_is_a_decision_commit() -> None:
    assert adr_shape.is_decision_commit("Release provenance must be verified for every artifact")


@pytest.mark.parametrize(
    "subject",
    [
        "Release 2.1.0 (#1234) of the app",
        "Release v12.10.3-beta.1 build",
        "release: publish the 2.1.0 artifacts",
        "release(npm)!: publish the 2.1.0 build",
        "Releases 4.0.0 to every store",
    ],
)
def test_release_bookkeeping_is_still_housekeeping(subject: str) -> None:
    assert len(subject) >= adr_shape.MIN_DECISION_SUBJECT_CHARS
    assert not adr_shape.is_decision_commit(subject)


# A8: the breaking token must open a footer paragraph


def test_a_breaking_line_under_prose_in_one_paragraph_is_not_a_footer() -> None:
    body = "Some body.\n\nThe following text is an example:\nBREAKING CHANGE: demo only"

    assert not adr_reason.breaking_change("feat: rename the field", body)


@pytest.mark.parametrize(
    "body",
    [
        "Body.\n\nBREAKING CHANGE: gone",
        "Body.\n\nReviewed-by: Z\nBREAKING CHANGE: gone",
        "Body.\n\nRefs #12\nBREAKING-CHANGE: gone\n\nSigned-off-by: a <a@b>",
    ],
)
def test_a_breaking_line_in_a_footer_paragraph_still_counts(body: str) -> None:
    assert adr_reason.breaking_change("feat: rename the field", body)


# A9 and A14: the shown prefix must hold a marker that qualifies the way scoring does

_PAD = "and keep every other part of the loader exactly as it was before this change "


def test_a_quoted_marker_in_the_kept_prefix_does_not_qualify_the_cut() -> None:
    sentence = 'We picked "because" as the word here ' + _PAD * 3 + "because the cache leaked."

    assert len(sentence) > adr_reason.REASON_MAX_CHARS
    assert _reason(sentence) is None


def test_a_quote_cut_by_the_cap_does_not_qualify_the_cut() -> None:
    sentence = "We kept " + _PAD * 2 + '"because ' + "words " * 30 + '" since it leaked memory.'

    assert sentence.index("because") < adr_reason.REASON_MAX_CHARS < sentence.rindex('"')
    assert _reason(sentence) is None


def test_a_medium_marker_without_its_problem_term_does_not_qualify_the_cut() -> None:
    sentence = (
        "We now parse the manifest with the streaming reader instead of the tree reader "
        + _PAD * 2
        + "because the tree reader crashed on large files."
    )

    assert sentence.index("because") > adr_reason.REASON_MAX_CHARS
    assert _reason(sentence) is None


@pytest.mark.parametrize(
    "sentence",
    [
        "We now read the manifest with the stream reader because the tree reader crashed, "
        + _PAD * 2,
        "We use the stream reader instead of the tree reader that broke on input, " + _PAD * 2,
    ],
)
def test_a_qualifying_marker_inside_the_cap_still_shows(sentence: str) -> None:
    shown = _reason(sentence)

    assert len(sentence) > adr_reason.REASON_MAX_CHARS
    assert shown is not None and shown.endswith("...")


def test_a_labelled_long_sentence_still_shows() -> None:
    shown = _reason("Why: " + "the stream reader is simpler " * 12)

    assert shown is not None and shown.endswith("...")


# A10 and A11: fences and comments are read in source order, and a fence needs its own closer


@pytest.mark.parametrize(
    "body",
    [
        f"{F3}html\n<!-- c\n{F3}\n\n{REASON}",
        f"<!--\n{F3}\n-->\n\n{REASON}",
        f"<!-- one --> {REASON} <!-- two -->",
        f"{F3}\nx\n{F3}  \n\n{REASON}",
        f"~~~~\n~~~\n~~~~\n\n{REASON}",
    ],
)
def test_the_reason_after_code_or_a_comment_survives(body: str) -> None:
    reason = _reason(body)

    assert reason is not None and "leaked memory" in reason


@pytest.mark.parametrize(
    "body",
    [
        f"{F4}\n{F3}\nThe sample says it failed because the disk was full.\n{F4}\n\nNo reason.",
        f"{F3}\n{F3}python\nThe sample says it failed because the disk was full.\n{F3}",
        "~~~~\n~~~\nThe sample says it failed because the disk was full.\n~~~~",
        f"{F3}\nThe sample says it failed because the disk was full.",
        f"<!-- {F3}\nThe sample says it failed because the disk was full.",
    ],
)
def test_text_inside_an_open_or_unmatched_fence_is_never_a_reason(body: str) -> None:
    assert _reason(body) is None


# A12: the rule-line test is linear and recognizes the same lines

_OLD_RULE_LINE = re.compile(r"^\s*[-=*_|: ]{3,}\s*\Z", re.ASCII)


def test_the_rule_line_test_matches_the_old_pattern_on_every_short_line() -> None:
    alphabet = [" ", "\t", "-", ":", "a", "\x0b"]
    for size in range(6):
        for chars in itertools.product(alphabet, repeat=size):
            line = "".join(chars)
            assert adr_reason._is_rule_line(line) is bool(_OLD_RULE_LINE.search(line)), repr(line)


@pytest.mark.parametrize(
    ("line", "rule"),
    [("-  ", True), ("  --", True), ("  \t---", True), ("---\t  ", True), ("  Because x", False)],
)
def test_padded_rules_stay_rules_and_prose_stays_prose(line: str, rule: bool) -> None:
    assert adr_reason._is_rule_line(line) is rule


@pytest.mark.parametrize("spaces", [2_000, 64 * 1024])
def test_a_long_leading_space_run_before_prose_is_linear(spaces: int) -> None:
    line = " " * spaces + "Because x"
    start = time.perf_counter()

    structural = adr_reason._is_structural_line(line)

    assert time.perf_counter() - start < LIMIT_S and not structural


# A13: a SHA-256 commit id in a commit URL


@pytest.mark.parametrize(
    ("digits", "found"), [(40, True), (64, True), (7, True), (41, False), (63, False), (65, False)]
)
def test_commit_urls_carry_sha1_or_sha256_ids(digits: int, found: bool) -> None:
    sha = "a" * digits

    got = adr_reason.commit_sha_of(f"https://github.com/o/r/commit/{sha}")

    assert got == (sha if found else None)


# Every new or changed pattern stays linear on 64 KiB of hostile input

_K = 64 * 1024
_HOSTILE = {
    "fence lines": f"{F3}\n" + "  ```x\n" * (_K // 7),
    "backtick run": "`" * _K,
    "backtick run then text": "`" * _K + "x`",
    "spaces before prose": " " * _K + "x",
    "tilde lines": "~~~\n" + "~~ ~\n" * (_K // 5),
    "comment openers": "<!--" * (_K // 4),
    "dashes after an opener": "<!--" + "-" * _K,
    "blank lines": "\n" * _K,
    "bump token": "bumps " + "a" * _K,
    "bump spaces": "Updates x" + " " * _K + "y",
    "bold marks": "**" * (_K // 2),
    "hash run": "#" * _K,
    "commit path": "/commit/" + "a" * _K,
}


@pytest.mark.parametrize("text", _HOSTILE.values(), ids=_HOSTILE.keys())
def test_the_new_patterns_are_linear_on_hostile_input(text: str) -> None:
    start = time.perf_counter()

    adr_shape.FENCED_BLOCK.sub("\n", text)
    adr_reason._CODE.sub("\n", text)
    adr_reason._DUMP_HEADING.search(text)
    adr_reason._BUMP_BODY.search(text)
    adr_reason.commit_sha_of(text)
    adr_shape.has_stated_rationale("feat: Switch to bounded queues", text)
    adr_reason.breaking_change("feat: x", text)

    assert time.perf_counter() - start < LIMIT_S
