"""The text check that keeps the two hole patterns free of a repeat, and its controls."""

from __future__ import annotations

import re

import adr_reason
import pytest

_MAX_OPTIONAL_ITEMS = 2  # the blank before the hole and the blank after it
_UNREAD_GROUP = "has (?, which this text check does not read"
_UNREAD_HASH = "has #, which this text check does not read"
_UNREAD_MARKS = (("(?", _UNREAD_GROUP), ("#", _UNREAD_HASH))
_HIDDEN_BY_COMMENT_GROUP = r"(?#[)\s*\s*(?#])"
_HIDDEN_BY_VERBOSE_COMMENT = "#[\n\\s*\\s*#]\n"
_HIDDEN_BY_INLINE_VERBOSE = "(?x)#[\n\\s*#]\n"
_LITERAL_STAR_CLASS = "[]*]"  # to the engine, one class that holds "]" and "*"


def _why_not_linear(pattern: str) -> list[str]:
    """What lets ``pattern`` cost more than a fixed number of steps per start position.

    A repeat (``*``, ``+`` or ``{``) can rescan a run from every start. A ``?`` cannot, but each
    one doubles the ways a failed match is retried. A pattern with no repeat and a few ``?``
    is linear whatever the input holds, so this needs no clock.

    This reads the pattern as text and does not parse it. It drops each escape, then each
    character class, and looks at what is left. A comment breaks that: the engine skips a
    comment, but the class strip pairs a ``[`` in one comment with a later ``]`` and takes the
    repeats between them out of the text. So a pattern that has ``(?`` or ``#`` after the
    escapes are gone is refused, and the refusal is the only reason given, because the rest of
    the scan is not reliable there. ``(?`` starts a comment group, and also each lookaround,
    non-capturing group and inline flag. ``#`` starts a comment under ``re.VERBOSE``, a flag
    the text does not show when the caller passes it to ``re.compile``.

    The refusal also takes a pattern that is safe: ``(\\s?)`` is ``(?)`` after the escape is
    gone, and ``[(?]`` and ``[#]`` hold the two marks as literals. A safe pattern can fail
    here. A pattern with a repeat cannot pass.

    With no comment, a bracket cannot hide a repeat. The class strip ends a class at the first
    ``]``, which is at or before the place the engine ends it, so the strip takes text only
    from inside a class. For ``[]*]`` it ends early and reports a literal ``*``.
    """
    unescaped = re.sub(r"\\.", "", pattern)
    unread = [reason for mark, reason in _UNREAD_MARKS if mark in unescaped]
    if unread:
        return unread
    bare = re.sub(r"\[[^\]]*\]", "", unescaped)
    reasons = [f"repeats with {mark}" for mark in "*+{" if mark in bare]
    if bare.count("?") > _MAX_OPTIONAL_ITEMS:
        reasons.append(
            f"has {bare.count('?')} optional items, over the limit of {_MAX_OPTIONAL_ITEMS}"
        )
    return reasons


def test_the_hole_patterns_are_linear_on_a_long_run_of_blanks() -> None:
    for pattern in (adr_reason._HOLE, adr_reason._HOLE_BEFORE_PUNCT):
        assert _why_not_linear(pattern.pattern) == [], pattern.pattern
    hole = adr_reason._URL_HOLE
    blanks = " " * 10000
    # The patterns still run on the long texts: a hole takes one blank from each side with it.
    for case, text, filled in (
        ("no hole", blanks + blanks, blanks + blanks),
        ("hole in the middle", blanks + hole + blanks, blanks[1:] + " " + blanks[1:]),
        ("hole at the start", hole + blanks + blanks, " " + blanks[1:] + blanks),
    ):
        assert adr_reason._HOLE.sub(" ", text) == filled, case
        assert adr_reason._HOLE_BEFORE_PUNCT.sub(r"\1", text) == text, case
    assert adr_reason._HOLE_BEFORE_PUNCT.sub(r"\1", blanks + hole + " ." + blanks) == (
        blanks[1:] + "." + blanks
    )


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        # Negative controls. The first is the upstream form: it takes seconds on the texts
        # above, where the shipped patterns take milliseconds.
        (r"\s*\ue000\s*", ["repeats with *"]),
        (r"\s+\ue000", ["repeats with +"]),
        (r"\s{0,}\ue000", ["repeats with {"]),
        (r"\s{1,5000}\ue000", ["repeats with {"]),
        (r"\s?\s?\s?\ue000", ["has 3 optional items, over the limit of 2"]),
        (r"\*\+\{\?\?\?[*+{?]\ue000\s?", []),  # escaped and in a class: none of these repeats
        # A comment hides a repeat: its "[" pairs with a later "]" and the class strip takes
        # the repeats between them out of the text. The first is the false pass found on #7797.
        (_HIDDEN_BY_COMMENT_GROUP, [_UNREAD_GROUP, _UNREAD_HASH]),  # "(?#" holds both marks
        (_HIDDEN_BY_VERBOSE_COMMENT, [_UNREAD_HASH]),  # a comment only under re.VERBOSE
        (_HIDDEN_BY_INLINE_VERBOSE, [_UNREAD_GROUP, _UNREAD_HASH]),  # the flag is in the text
        # Every "(?" form is refused, and the refusal is the only reason given.
        (r"(?=\s*)\ue000", [_UNREAD_GROUP]),  # lookahead
        (r"(?:\s?)\ue000", [_UNREAD_GROUP]),  # non-capturing group
        (r"(?i)\s?\ue000", [_UNREAD_GROUP]),  # inline flag
        # Refused with no comment in the pattern: the safe direction.
        (r"(\s?)\ue000", [_UNREAD_GROUP]),  # the escape between "(" and "?" is gone by then
        (r"[(?#]\ue000", [_UNREAD_GROUP, _UNREAD_HASH]),  # literal in a class
        # Not refused: an escaped mark is gone before the check looks for one.
        (r"\(\?\#\ue000\s?", []),
        # An unbalanced bracket in a class hides nothing: the repeat after the class stays.
        (r"[]]\s*\ue000", ["repeats with *"]),
        (r"[^]]\s*\ue000", ["repeats with *"]),
        (r"[[]\s*\ue000", ["repeats with *"]),
        # No repeat, and still a reason: the class strip stops at the first "]" and leaves a
        # literal "*" behind. A safe pattern fails here; a pattern with a repeat never passes.
        (_LITERAL_STAR_CLASS + r"\ue000", ["repeats with *"]),
    ],
)
def test_the_linear_check_fails_a_pattern_that_can_rescan(
    pattern: str, expected: list[str]
) -> None:
    assert _why_not_linear(pattern) == expected


@pytest.mark.parametrize(
    ("pattern", "flags"),
    [
        (_HIDDEN_BY_COMMENT_GROUP, 0),
        (_HIDDEN_BY_VERBOSE_COMMENT, re.VERBOSE),
        (_HIDDEN_BY_INLINE_VERBOSE, 0),
    ],
)
def test_the_hidden_repeat_controls_do_repeat(pattern: str, flags: int) -> None:
    # No clock: a pattern with no repeat matches a run up to one fixed length and no longer.
    compiled = re.compile(pattern, flags)
    assert compiled.fullmatch(" " * 50)
    assert compiled.fullmatch(" " * 5000)


def test_the_verbose_comment_control_has_no_repeat_without_the_flag() -> None:
    # The text is the same with and without the flag, so the check cannot tell which it gets.
    # Without the flag it is a "#", one class and a newline: three characters, no more.
    plain = re.compile(_HIDDEN_BY_VERBOSE_COMMENT)
    assert plain.fullmatch("#*\n")
    assert plain.fullmatch("#" + " " * 50 + "\n") is None
    assert plain.fullmatch(" " * 50) is None


def test_a_bracket_first_in_a_class_is_a_literal_to_the_engine() -> None:
    # The engine ends this class at the second "]", after the place the class strip ends it.
    literal = re.compile(_LITERAL_STAR_CLASS)
    assert literal.fullmatch("*")
    assert literal.fullmatch("]")
    assert literal.fullmatch("**") is None
