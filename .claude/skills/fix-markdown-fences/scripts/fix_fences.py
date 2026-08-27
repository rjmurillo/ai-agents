#!/usr/bin/env python3
# taste-lint: ignore file-size
# Over the 500-line ceiling. No exact total here: this comment adds lines to
# the file it measures, so the figure was already wrong when written. That
# applies to the class total too: this comment said `roughly 150` while
# `_ListContainers` had grown past 250, so the sentence warning about stale
# counts carried one. No number here either. Most of this file is
# `_ListContainers`,
# which is duplicated byte-for-byte in prose-self-check because the two skills
# ship as separate plugin directories and neither is on the other's import
# path. The real fix is to move that class to the plugin's shared lib, which
# both skills can already reach through the ADR-047 inline bootstrap; that is
# a change to two skills' vendoring surface, so it is not being made inside a
# review round on an unrelated fix. Scoped to file-size only; complexity and
# every other rule still apply.
"""Detect and repair malformed markdown code fence closings.

This replaces a line-by-line scan the agent used to run by hand. Fence
tracking is a finite state machine over text, so it belongs in code: the
model reads the report instead of simulating the parser.

What counts as a defect:

- ``malformed_closing``: while a block is open, a line closes it with the
  right fence characters but carries an info string (```` ```python ````
  instead of ```` ``` ````). Renderers do not treat it as a closing fence,
  so the block bleeds into the following prose. Repair inserts a bare
  closing fence above the line and lets the line open the next block, which
  is the behavior this skill has always documented.
- ``unclosed_block``: the file ends with a block still open. Repair appends
  a bare closing fence.

Fence matching follows CommonMark rather than the naive ```` ```(\\w+) ````
pattern this script used to carry (Issue-free defect found while wiring the
script into SKILL.md):

- A fence is three or more backticks or three or more tildes.
- A closing fence uses the SAME character and is at least as long as the
  opening fence. That length rule is what keeps a ```` ```python ```` line
  inside a four-backtick container block as literal example text. The old
  parser ignored length and inserted a stray fence into every documentation
  file that shows fenced markdown inside a wider fence.
- A backtick opening fence whose info string contains a backtick is not a
  fence (CommonMark), so an inline-code run cannot open a block.

Line endings and the presence or absence of a trailing newline are
preserved. The old parser rejoined on ``\\n`` and appended the repair after
the trailing empty line, which added a blank line and dropped the final
newline.

Reporting is the default and writing requires ``--write``. A repair is a
best-effort reading of an ambiguous file: where the author meant a wider
container fence, the inserted closing fence is not the fix they want. The
agent reads the report, decides, and only then writes.

EXIT CODES (ADR-035):
  0 - No defects found, or `--write` repaired every defect it found.
  1 - Report mode (the default): at least one defect found. Nothing written.
  2 - Configuration error: a requested path does not exist, or a file could
      not be read or written.
"""

from __future__ import annotations

import argparse
import codecs
import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

# CommonMark caps a fence marker at three spaces of indent; past that it is an
# indented code block and the backticks are literal content. Honoring that cap
# is what keeps `--write` from appending a fence to a file that documents a
# bare fence inside an indented block. The cap is measured from the innermost
# open list item, not from column zero, so a fence indented four spaces inside
# a list item is still a fence. See `_ListContainers`.
_FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_MAX_FENCE_INDENT = 3


_LIST_MARKER = re.compile(
    r"^(?P<indent>[ \t]*)"
    # ASCII digits only. Python's `\d` also matches Unicode decimal digits, so
    # `\u0661. item` opened a list here and CommonMark read it as a paragraph.
    r"(?:(?P<bullet>[-*+])|(?P<number>[0-9]{1,9})(?P<delim>[.)]))"
    r"(?P<pad>[ \t]*)(?P<rest>.*)$"
)
_ATX_HEADING = re.compile(r"^#{1,6}([ \t]|$)")
_THEMATIC_BREAK = re.compile(r"^(?:([-*_])[ \t]*)(?:\1[ \t]*){2,}$")
_BLOCK_QUOTE = re.compile(r"^>")
# Only a setext underline when a paragraph is already open; `===` on its own is
# ordinary prose. `---` reaches the same conclusion through _THEMATIC_BREAK, so
# the gap was `=`, which matches nothing else.
_SETEXT_UNDERLINE = re.compile(r"^(?:=+|-+)[ \t]*$")
# A link reference definition, validated rather than sniffed. An earlier
# version required only `\\S` after the colon, which accepted `[foo]: <broken`
# and `[foo]: /url "unclosed`. CommonMark reads both as paragraph text, so
# clearing paragraph state there let `--write` append a fence to a document
# holding no fence at all. Measured against the reference parser over 22
# destination and title shapes; these three patterns agree with it on all 22.
#
# The title is a quoted or parenthesised run. Each form may carry a
# backslash-escaped copy of its own delimiter, which is why every alternative
# spells the escape: `[^"]*` stopped at the backslash in `"a\\"b"` and read a
# valid title as prose. CommonMark forbids an UNESCAPED parenthesis inside the
# parenthesised form, so one level is the whole grammar there and a pattern
# can spell it; the destination cannot say the same, hence the scanner below.
_LINK_TITLE = r"(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\))"
# `\s`, not `[ \t]`. CommonMark normalises a label before comparing it, so a
# label holding only whitespace normalises to empty and the line is not a
# definition. The guard tested space and tab alone, so `[\xa0]: /url` parsed
# here as a definition, cleared paragraph state the reference parser keeps,
# and `--write` appended a fence to a document holding none.
_LINK_LABEL = r"\[(?!\s*\])(?:[^\[\]\\]|\\.)*\]"
_LINK_TITLE_ONLY = re.compile(rf"^{_LINK_TITLE}[ \t]*$")
# CommonMark also lets the destination start on the line AFTER the label. The
# label line stays paragraph text until a valid destination proves otherwise,
# which is why `_awaiting_link_destination` defers rather than deciding: with
# `[foo]:` followed directly by `2.`, the reference parser keeps the paragraph
# and vetoes the marker, and deciding early would break that.
_LINK_LABEL_ONLY = re.compile(rf"^{_LINK_LABEL}:[ \t]*$")
_LINK_LABEL_COLON = re.compile(rf"^{_LINK_LABEL}:[ \t]*")


def _angle_destination_end(body: str, start: int) -> int | None:
    """Return the index just past the `<...>` destination at *start*, or None.

    Character by character, not `find(">")`. CommonMark lets the angle form
    carry an ESCAPED copy of either delimiter, so `find` stopped at the `\\>`
    in `<foo\\>bar>` and a substring test rejected the `\\<` in `<foo\\<bar>`.
    Both are valid definitions, both were read as prose, and `--write` then
    appended a fence to a balanced document.
    """
    index = start + 1
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            index += 2
            continue
        if char == "<":
            return None  # an UNESCAPED `<` may not appear inside
        if char == ">":
            return index + 1
        index += 1
    return None  # the angle form never closed


def _link_destination_end(body: str, start: int) -> int | None:
    """Return the index just past the link destination at *start*, or None.

    The bracketless destination form allows parentheses at ANY nesting depth
    so long as they balance. A regex alternative can only spell a fixed depth,
    and the one that shipped spelled a single level, so `[foo]: /u(r(l))` was
    read as prose here and as a definition by the reference parser. That kept
    a paragraph open, vetoed the following list marker, and let `--write`
    append a fence to a balanced document. A scanner has no depth ceiling to
    get wrong; the reference parser accepts four levels and offers no reason
    to believe it stops there.

    The angle form is delegated but tested first, because a bare run must not
    begin with `<`: letting it swallow `<broken` is the defect this grammar
    exists to prevent.
    """
    if start < len(body) and body[start] == "<":
        return _angle_destination_end(body, start)
    index, depth = start, 0
    while index < len(body):
        char = body[index]
        if char in " \t":
            break
        if char == "\\" and index + 1 < len(body):
            index += 2  # an escaped character never counts as a delimiter
            continue
        if "\x01" <= char <= "\x1f" or char == "\x7f":
            # A bare destination may not carry an ASCII control character.
            # Measured over the whole range: the reference parser rejects
            # every one of U+0001 to U+0020 and U+007F, and accepts only
            # U+0000, which it replaces with U+FFFD before parsing. Space and
            # tab are already the break above, so this covers the other 29.
            # We accepted all of them and so read a definition where the
            # reference parser reads a paragraph, which made the scanner MISS
            # a genuinely unclosed fence rather than invent one.
            return None
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return None  # a closer with no opener
        index += 1
    if depth != 0 or index == start:
        return None  # unbalanced, or no destination at all
    return index


_TITLE_CLOSERS = {'"': '"', "'": "'", "(": ")"}


def _title_end(body: str, start: int) -> int | str | None:
    """Return the index past a title at *start*, the delimiter it awaits, or None.

    A CommonMark title may run across lines until its closing delimiter, so a
    title that opens here and does not close is not a failure: it is a state.
    A string result IS that state, the delimiter still expected; an int is a
    title complete on this line. Callers distinguish them with `isinstance`,
    because both are truthy and only one means "done".
    """
    if start >= len(body):
        return None
    closer = _TITLE_CLOSERS.get(body[start])
    if closer is None:
        return None
    index = start + 1
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            index += 2  # a delimiter may be escaped inside its own title
            continue
        if char == closer:
            return index + 1
        if closer == ")" and char == "(":
            return None  # an UNESCAPED `(` may not appear in a parenthesised title
        index += 1
    return closer


def _label_opens(body: str) -> bool:
    """Return True when a link label opens in *body* and does not close on it.

    CommonMark lets a label span lines, which the single-line patterns cannot
    express: `[fo` / `o]: /url` is a definition to the reference parser and was
    prose here, so the marker below it was vetoed and `--write` appended a
    fence to a balanced document.
    """
    if not body.startswith("["):
        return False
    index = 1
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            index += 2
            continue
        if char == "]":
            return False  # it closed here, so the single-line patterns own it
        if char == "[":
            return False  # an UNESCAPED `[` is not allowed inside a label
        index += 1
    return True


@dataclass(frozen=True, slots=True)
class _Definition:
    """What a parsed link reference definition still expects.

    `awaiting_title` means it carries none yet, so a bare title may continue it
    on the next line. `open_title` is the delimiter a title opened on this line
    is still waiting for. Both empty means the definition is complete.
    """

    awaiting_title: bool = False
    open_title: str | None = None


def _link_tail(body: str, start: int) -> _Definition | None:
    """Return what the definition beginning at *start* still expects, or None.

    None means the rest of the line is not a destination optionally followed by
    one title, so the line is prose. Callers must test `is None` rather than
    truthiness, because a complete definition is a falsy-looking empty record.
    """
    end = _link_destination_end(body, start)
    if end is None:
        return None
    rest = body[end:]
    if not rest.strip(" \t"):
        return _Definition(awaiting_title=True)
    separated = rest.lstrip(" \t")
    if len(separated) == len(rest):
        return None  # a title must be separated from the destination
    result = _title_end(body, end + len(rest) - len(separated))
    if result is None:
        return None
    if isinstance(result, str):
        return _Definition(open_title=result)
    return None if body[result:].strip(" \t") else _Definition()


def _bare_title(body: str) -> bool | str | None:
    """Return True for a complete title line, the awaited delimiter, or None.

    This is the next-line form, which may itself open a multi-line title.
    """
    result = _title_end(body, 0)
    if result is None or isinstance(result, str):
        return result
    return True if not body[result:].strip(" \t") else None


def _link_reference(body: str) -> _Definition | None:
    """Return what a same-line definition still expects, or None for prose."""
    match = _LINK_LABEL_COLON.match(body)
    return None if match is None else _link_tail(body, match.end())
_MAX_LIST_PAD = 4


def _indent_width(text: str) -> int:
    """Return the column *text* occupies, tabs expanded to a 4-column stop."""
    return len(text.expandtabs(4))


def _is_blank(text: str) -> bool:
    """Return True when *text* is empty or only spaces and tabs.

    Not `str.strip()`, which also removes U+00A0 and the rest of Unicode
    whitespace. CommonMark counts only spaces and tabs, so `-\u00a0` is
    paragraph text rather than an empty list item, and a line holding one
    non-breaking space is content rather than a blank that leaves a container
    open.
    """
    return not text.strip(" \t")

def _container_closed(line: str, base: int) -> bool:
    """Return True when *line* dedents out of the container holding a block.

    A fenced block inside a list item ends when the document leaves that item,
    even without a closing marker. Tracking a block's lifetime independently of
    its container left the block open to EOF, so `--write` appended a closing
    fence to a document CommonMark already considers complete. A top-level
    block has base 0 and can never be closed this way.
    """
    if base == 0 or _is_blank(line):
        return False
    return _indent_width(line[: len(line) - len(line.lstrip(" \t"))]) < base


class _ListContainers:
    """The content column of the innermost open list item, tracked line by line.

    CommonMark measures a fence marker's indent from its containing block, not
    from column zero, so a marker four spaces deep inside a list item opens a
    fence while the identical line at top level is indented code.

    Call order per line, outside a fenced block: `sync`, then `over_indented`,
    then either `opened_fence` when a fence opened or `observe` when none did.
    `sync` before classifying is what lets a dedent close a stale container
    before the fence test reads its base. Do not call any of these for lines
    inside a fenced block: CommonMark reads no list markers there.

    Deciding whether a marker line opens a list item is most of CommonMark's
    list grammar, and every rule below was a real defect first: reported in
    review, then reproduced against `markdown-it-py` before being fixed. The
    module is checked against that parser rather than against expectations,
    because expectations are what got each of these wrong.

    1. A marker more than three columns past the current content column is
       itself indented code, so it opens nothing.
    2. Padding of five or more columns after the marker is not all
       indentation. The content column is the marker plus one.
    3. A marker with no content on its line is an empty item, whose content
       column is the marker plus one.
    4. A list may interrupt a paragraph only when the item is non-empty and,
       if ordered, starts at 1. Leading zeros do not change the start value,
       so `01.` and `001.` may interrupt and `003.` may not.
    5. A thematic break is never a list item, even though `* * *` and `- - -`
       both match the bullet grammar.
    6. A paragraph continuation line may drop below its container's indent
       without closing it, so a dedent only closes containers when the line
       actually starts a new block.
    7. Paragraph state follows blocks, not raw lines. A fence, an ATX
       heading, and a thematic break all end a paragraph, and each is
       recognized relative to the container rather than to column zero.
    8. An item may begin with at most one blank line, so a blank directly
       after an empty marker closes it rather than continuing it.
    9. A marker line's remainder is re-parsed inside the item it just opened,
       so `- - a` opens two items and a fence marker after `- ` opens a block.
       `observe` returns the column it opened for exactly this, and leaves
       paragraph state to that second pass rather than guessing it here.
    10. A fenced block ends when the item holding it ends, with no closing
        marker, so a line that dedents below the block's container closes it.
        See `_container_closed`.
    11. A setext underline ends the paragraph above it. `---` already reached
        that conclusion as a thematic break, so only `=` was missing, and a
        list could not interrupt after a setext H1.
    12. A marker line does not itself open a paragraph. Rule 9's second pass
        sets that state from the remainder, so `- 2. item` opens both items
        instead of rejecting the nested one as a paragraph interruption.
    13. An ordered marker is ASCII digits only. Python's regex `\\d`
        shorthand also matches Unicode decimal digits, so a line led by
        U+0661 ARABIC-INDIC DIGIT ONE opened a list here while CommonMark
        read it as a paragraph.
    14. Blank means spaces and tabs, not `str.strip()`. Unicode whitespace
        made a line holding one U+00A0 look blank, which left a container
        open past its item, and made `-` plus U+00A0 look like an empty item
        when CommonMark reads it as paragraph text. See `_is_blank`.
        It binds three operands, and each was a separate defect: blank lines,
        a marker line's remainder, and a closing fence's info string. A closing
        fence may be followed only by spaces and tabs, so `str.strip()` there
        accepted U+00A0 as blank, closed the block early, and let `--write`
        rewrite a document the reference parser reads as well formed. Neither
        the corpus nor the fuzzer could reach that one: the generator emitted
        no Unicode whitespace at all until it was widened for exactly this.

    15. A paragraph ends when the item holding it ends. Rule 4 stops a marker
        interrupting an open paragraph, but that veto is scoped to the item
        the paragraph lives in. A marker indented below the content column
        closes that item, so the paragraph closes with it and the marker is
        judged at the outer level, where no paragraph is open. Without this,
        `- text` / `  more` / `2. ```` ` left the paragraph open across the
        dedent, rule 4 vetoed the `2.`, and the fence went unseen. Both
        halves are load-bearing and neither moves a measurement alone: the
        veto has to consult the indent (`_outdents`) AND `sync` has to clear
        the paragraph when it pops the container. Fixing only the first pops
        the container and then re-applies the veto at base 0; fixing only the
        second is dead code, because `_starts_a_block` returns False and
        `sync` returns at the lazy-continuation guard before it ever pops.

    16. A link reference definition is its own leaf block, not a paragraph.
        `[foo]: /url` left paragraph state open, rule 4 then vetoed a
        following `2.`, the real closer read as a fresh opener, and
        `--write` appended a stray fence to a document the reference parser
        reads as balanced. It is scoped both ways, and each half was
        measured rather than assumed: a definition cannot INTERRUPT an open
        paragraph, so the test is gated on `not _in_paragraph`; and a bare
        title on the NEXT line continues a definition that carried none,
        which is why `_awaiting_link_title` exists. An empty label, four
        columns of indent, and a second title once the definition already
        has one are all NOT definitions, and each has a curated case that
        passed before this rule landed.

        The destination and title must be COMPLETE, which the first
        version of this rule did not check: it required only one
        non-space character after the colon, so `[foo]: <broken` and
        `[foo]: /url "unclosed` cleared paragraph state and `--write`
        appended a fence to a document holding no fence at all. That was
        a corruption introduced by the fix for a corruption. The three
        patterns are measured against the reference parser over 22
        destination and title shapes and agree on all 22.

        CommonMark also lets the destination start on the line after the
        label, and leaving that unhandled was a corruption too, not the
        harmless miss an earlier note claimed. `_awaiting_link_destination`
        defers the decision rather than making it early: the label line
        stays paragraph text until a valid destination proves otherwise,
        because `[foo]:` followed directly by `2.` keeps its paragraph and
        vetoes the marker.

    Rules 9 and 10 were both documented as deliberate limitations for one
    commit, on the reasoning that each only made the scanners miss a fence,
    which is the safe direction for a tool that writes files. That reasoning
    was wrong twice. Both instead left a block open past its real end, so
    `--write` appended a closing fence to documents CommonMark already
    considers complete. `- - ``` ` was additionally a regression from this
    module's own container work, since the flat scanner never opened a
    container there at all. Prefer measuring a failure's direction over
    reasoning about it.

    Blockquotes are the one container this does not track, and that gap is
    stated here with the measurement rather than with the same argument that
    failed twice above. A `>` prefix is never stripped, so a fence inside a
    blockquote is invisible. `--write` was run over seven blockquote shapes:
    balanced, unclosed, followed by a top-level fence, lazily closed, with a
    malformed closer, nested in a list item, and carrying an info string. It
    changed two, and the reference parser reads both of those as genuinely
    unclosed, so the writes are correct. That is HALF the gap, and saying it
    was the whole gap was wrong for two rounds. The other half is a blockquote
    INTERRUPTING a paragraph: CommonMark ends the paragraph there and lazily
    continues the quote, so a following `2.` opens a list, while we keep the
    paragraph open, rule 4 vetoes the marker, and `--write` appends a closer to
    a balanced document. Two of twelve measured shapes, and it reproduces on
    `main` with no link reference definition present, so it belongs to the
    container model rather than to rule 16. Four such markers exist in this
    repository, in two archived session logs, and they are the whole of the
    remaining under-masking. Closing it means consuming line prefixes through
    the entire
    scan rather than reasoning in columns, which is a larger change than any
    rule above.
    """

    __slots__ = (
        "_awaiting_link_destination",
        "_awaiting_link_title",
        "_columns",
        "_in_paragraph",
        "_item_still_empty",
        "_open_label_blank",
        "_open_title",
    )

    def __init__(self) -> None:
        self._columns: list[int] = []
        self._in_paragraph = False
        self._item_still_empty = False
        self._awaiting_link_title = False
        self._awaiting_link_destination = False
        self._open_title: str | None = None
        self._open_label_blank: bool | None = None

    def over_indented(self, indent: str) -> bool:
        """Return True when *indent* puts the marker inside an indented code block."""
        return _indent_width(indent) - self._base() > _MAX_FENCE_INDENT

    def sync(self, line: str) -> None:
        """Close containers that *line* has dedented out of."""
        if _is_blank(line):
            self._in_paragraph = False  # a blank line ends any open paragraph
            self._awaiting_link_title = False  # and ends a pending definition
            self._awaiting_link_destination = False
            self._open_title = None  # an unclosed title dies with the blank too
            self._open_label_blank = None  # and so does an unclosed label
            if self._item_still_empty and self._columns:
                # Rule 8: an item may begin with at most one blank line, so a
                # blank directly after an empty marker closes it. Without this
                # the stale column made the next indented block look list-nested,
                # and `--write` would then fence literal indented code.
                self._columns.pop()
                self._item_still_empty = False
            return
        # A definition still waiting for its destination or title is an open
        # leaf block exactly as a paragraph is, so a line that continues it is
        # a lazy continuation and must not close the item holding it. Reading
        # only `_in_paragraph` here popped the item on a dedented title, the
        # fence below it then opened at column zero instead of inside the item,
        # nothing could close it, and `--write` appended to a balanced document.
        pending = (
            self._awaiting_link_title
            or self._awaiting_link_destination
            or self._open_title is not None
            or self._open_label_blank is not None
        )
        if (self._in_paragraph or pending) and not self._starts_a_block(line):
            return  # rule 6: a lazy continuation keeps its container open
        width = _indent_width(line[: len(line) - len(line.lstrip(" \t"))])
        while self._columns and width < self._columns[-1]:
            self._columns.pop()
            self._in_paragraph = False  # rule 15: it closed with the item

    def opened_fence(self) -> None:
        """Record that a fenced block opened on this line."""
        self._in_paragraph = False  # rule 7: a fence ends the paragraph
        self._item_still_empty = False  # the fence is the item's content
        # Rule 16: a fence interrupts a link reference definition, and the
        # scanner freezes container state for the whole fenced block, so the
        # caller never observes the lines between the opener and the closer.
        # Left set, a pending destination or title matched the first line
        # AFTER the block, which cleared paragraph state that CommonMark keeps
        # open and let `--write` append a closer to a balanced document.
        self._awaiting_link_title = False
        self._awaiting_link_destination = False
        self._open_title = None
        self._open_label_blank = None

    def _consume_open_label(self, line: str) -> None:
        """Advance a label that opened on an earlier line over *line*.

        Whether the label is blank is the only thing anything reads out of it,
        so that one bit is all the scanner carries. Accumulating the text
        instead copied the whole run on every continuation line, which made an
        unmatched `[` near the top of a file quadratic in the lines below it.
        Measured over plain prose before this change: 2,000 lines scanned at
        7.5us per line and 32,000 at 42.1us, and doubling the file multiplied
        the time by 3 to 4 rather than by 2.
        """
        index = 0
        while index < len(line):
            char = line[index]
            if char == "\\" and index + 1 < len(line):
                index += 2
                continue
            if char == "]":
                blank = self._open_label_blank and not line[:index].strip()
                self._finish_open_label(bool(blank), line[index + 1 :])
                return
            if char == "[":
                # The single-line `_LINK_LABEL` spells `[^\[\]\\]` and so has
                # always rejected an unescaped `[`. This path did not, which
                # made the multi-line label looser than the one-line one for
                # no reason anyone chose.
                self._open_label_blank = None
                self._in_paragraph = True
                return
            index += 1
        self._open_label_blank = self._open_label_blank and not line.strip()

    def _finish_open_label(self, blank: bool, rest: str) -> None:
        """Decide what a label closing on this line leaves open.

        *blank* records whether every line of the label was whitespace. A
        label normalising to empty is not a definition, and neither is one
        whose `]` is not followed by a colon; both make the whole run prose.
        """
        self._open_label_blank = None
        if blank or not rest.startswith(":"):
            self._in_paragraph = True
            return
        after = rest[1:]
        tail = after.lstrip(" \t")
        if not tail:
            self._in_paragraph = True  # the destination may still arrive
            self._awaiting_link_destination = True
            return
        result = _link_tail(tail, 0)
        if result is None:
            self._in_paragraph = True
            return
        self._in_paragraph = False
        self._awaiting_link_title = result.awaiting_title
        self._open_title = result.open_title

    def _consume_open_title(self, line: str) -> None:
        """Advance a title that opened on an earlier line over *line*.

        The definition completes only when the closing delimiter arrives with
        nothing but whitespace behind it; anything else makes the whole run
        ordinary paragraph text, which is what `_in_paragraph` then records.
        """
        closer = self._open_title
        index = 0
        while index < len(line):
            char = line[index]
            if char == "\\" and index + 1 < len(line):
                index += 2
                continue
            if char == closer:
                self._open_title = None
                self._in_paragraph = bool(line[index + 1 :].strip(" \t"))
                return
            if closer == ")" and char == "(":
                # Same asymmetry as the label above: `_title_end` rejects an
                # unescaped `(` inside a parenthesised title on one line, and
                # this path accepted it across lines.
                self._open_title = None
                self._in_paragraph = True
                return
            index += 1

    def observe(self, line: str) -> int | None:
        """Open a container when *line* starts a list item, then track paragraphs.

        Returns the content column it opened, so the caller can re-scan the
        rest of the line against it. CommonMark re-parses a marker line's
        remainder inside the item the marker just opened, which is how
        `- ``` ` opens a fenced block and `- - a` opens two items.
        """
        if _is_blank(line):
            return None  # `sync` already ended the paragraph
        if self._open_label_blank is not None:
            if not self._starts_a_block(line):
                self._consume_open_label(line)
                return None
            self._open_label_blank = None
            self._in_paragraph = True
        if self._open_title is not None:
            if not self._starts_a_block(line):
                # Every character of this line belongs to a title that opened
                # earlier, so nothing on it starts a block.
                self._consume_open_title(line)
                return None
            # A block start ABANDONS the definition. Measured against the
            # reference parser over thirteen continuation shapes: a list
            # marker of either kind, an ATX heading, a block quote and a fence
            # each leave the whole run one paragraph, while plain text, two or
            # four columns of indent, and lines that only look like a thematic
            # break or a setext underline all let the title finish. What was
            # a definition is therefore paragraph text, and this line is then
            # judged against that paragraph rather than against a clean slate.
            self._open_title = None
            self._in_paragraph = True
        item = self._list_item(line)
        if item is not None:
            column, has_content = item
            self._columns.append(column)
            # Not `has_content`. The caller re-parses the remainder inside the
            # item just opened, and that pass sets the state from what the
            # remainder actually is. Setting it here first made `- 2. item`
            # mark the outer item as a paragraph, so the nested `2.` was then
            # rejected as an interruption and never opened its own container.
            self._in_paragraph = False
            self._item_still_empty = not has_content
            # A new item is a new container, and a definition still waiting for
            # its destination or title belonged to the one outside it. Left
            # set, the caller's re-parse of the marker's remainder booked that
            # remainder as the OLD definition's destination, so paragraph state
            # stayed clear, a later dedent closed the item early, and `--write`
            # appended a closer to a balanced document.
            self._awaiting_link_title = False
            self._awaiting_link_destination = False
            self._open_title = None
            self._open_label_blank = None
            return column
        self._item_still_empty = False  # this line is the item's first content
        content = self._relative(line)
        body = content.lstrip(" ")
        # A definition still waiting for its destination or its title is the
        # exception to the indent veto below. Its continuation belongs to the
        # SAME leaf block, so CommonMark strips the indent rather than reading
        # indented code. With the veto in front of it, `[foo]:` followed by a
        # four-column `/url` left the label line a paragraph, rule 4 then
        # vetoed the marker under it, the real closing fence became a fresh
        # opener, and `--write` appended a closer to a balanced document.
        continues_definition = (
            self._awaiting_link_destination and _link_tail(body, 0) is not None
        ) or (self._awaiting_link_title and bool(_LINK_TITLE_ONLY.match(body)))
        if len(content) - len(body) > _MAX_FENCE_INDENT and not continues_definition:
            # Indented code when no paragraph is open, a lazy continuation when
            # one is. Neither changes the state, and both differ from prose.
            # But an indented code block is its own leaf block, so it also ENDS
            # a definition still waiting. A lazy continuation does not, which is
            # why this is gated on there being no open paragraph.
            if not self._in_paragraph:
                self._awaiting_link_title = False
                self._awaiting_link_destination = False
            return None
        # None means "not one"; False means "one carrying no title yet", which
        # is why these are tested with `is None` and never for truthiness.
        definition = None if self._in_paragraph else _link_reference(body)
        dest_line = _link_tail(body, 0) if self._awaiting_link_destination else None
        title_line = _bare_title(body) if self._awaiting_link_title else None
        label_only = not self._in_paragraph and bool(_LINK_LABEL_ONLY.match(body))
        label_opens = not self._in_paragraph and _label_opens(body)
        self._in_paragraph = not (
            _ATX_HEADING.match(body)
            or _THEMATIC_BREAK.match(body)
            or _starts_fence(body)
            or _BLOCK_QUOTE.match(body)
            or (self._in_paragraph and _SETEXT_UNDERLINE.match(body))
            or definition is not None
            or title_line is not None
            or dest_line is not None
        )
        self._awaiting_link_destination = label_only
        self._awaiting_link_title = (
            definition is not None and definition.awaiting_title
        ) or (dest_line is not None and dest_line.awaiting_title)
        # A title may open on this line and close lines later, so record the
        # delimiter it is waiting for rather than rejecting the definition.
        self._open_title = (
            (definition.open_title if definition is not None else None)
            or (dest_line.open_title if dest_line is not None else None)
            or (title_line if isinstance(title_line, str) else None)
        )
        # A label may open here and close lines later, at which point the rest
        # of THAT line carries the destination and title.
        self._open_label_blank = not body[1:].strip() if label_opens else None
        return None

    def _outdents(self, indent: str) -> bool:
        """Return True when a marker at *indent* closes the innermost item.

        Rule 15: rule 4 stops a marker interrupting a paragraph only while
        the marker sits inside the item that holds it. A marker indented
        less than the content column closes that item, and the paragraph
        closes with it, so the marker is judged at the outer level where
        no paragraph is open.
        """
        return _indent_width(indent) < self._base()

    def base(self) -> int:
        """Return the innermost open content column, or 0 at top level."""
        return self._columns[-1] if self._columns else 0

    def _base(self) -> int:
        return self.base()

    def _relative(self, line: str) -> str:
        """Return *line* with the container's content column removed."""
        expanded = line.expandtabs(4)
        stripped = expanded.lstrip(" ")
        indent = len(expanded) - len(stripped)
        return " " * max(0, indent - self._base()) + stripped

    def _starts_a_block(self, line: str) -> bool:
        """Return True when *line* begins a block rather than continuing a paragraph."""
        content = self._relative(line)
        body = content.lstrip(" ")
        if len(content) - len(body) > _MAX_FENCE_INDENT:
            return False  # indented code cannot interrupt a paragraph
        return bool(
            _starts_fence(body)
            or _BLOCK_QUOTE.match(body)
            or _ATX_HEADING.match(body)
            or _THEMATIC_BREAK.match(body)
            or self._list_item(line) is not None
        )

    def _list_item(self, line: str) -> tuple[int, bool] | None:
        """Return *line*'s content column and whether its item has content.

        None when the line opens no list item. Returning both from the one
        match keeps the caller from re-matching a pattern that has already
        been shown to apply.
        """
        content = self._relative(line)
        body = content.lstrip(" ")
        if len(content) - len(body) > _MAX_FENCE_INDENT:
            return None  # rule 1: the marker is itself indented code
        if _THEMATIC_BREAK.match(body):
            return None  # rule 5
        match = _LIST_MARKER.match(line)
        if match is None:
            return None
        number = match.group("number")
        marker = match.group("bullet") or number + match.group("delim")
        marker_end = _indent_width(match.group("indent") + marker)
        empty = _is_blank(match.group("rest"))
        blocked = empty or (number is not None and int(number) != 1)
        if self._in_paragraph and blocked and not self._outdents(match.group("indent")):
            return None  # rule 4: this marker cannot interrupt a paragraph
        if empty:
            return marker_end + 1, False  # rule 3
        pad = _indent_width(match.group("indent") + marker + match.group("pad")) - marker_end
        if pad == 0:
            return None  # a marker needs whitespace before its content
        return marker_end + (1 if pad > _MAX_LIST_PAD else pad), True  # rule 2


# Real line terminators only. `str.splitlines` also splits on \x0b, \x0c,
# \x1c-\x1e, U+0085, U+2028 and U+2029, which would delete those characters
# from a repaired file and break one prose line into two.
_LINE_SPLIT_RE = re.compile(r"(\r\n|\r|\n)")

_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})

MALFORMED_CLOSING = "malformed_closing"
UNCLOSED_BLOCK = "unclosed_block"


@dataclass(frozen=True)
class Defect:
    """One fence problem located in a file."""

    line: int
    kind: str
    text: str


@dataclass(frozen=True)
class _OpenFence:
    """The fence that opened the block currently being scanned."""

    char: str
    length: int
    indent: str

    @property
    def closing(self) -> str:
        return self.indent + self.char * self.length


def _fence_match(line: str) -> re.Match[str] | None:
    """Return the match when *line* is a fence opener, ignoring its indent.

    CommonMark: a backtick opening fence may not carry a backtick in its info
    string, which is what keeps ``a ``` b`` from opening a block. Every opener
    path goes through here so none of them can forget that rule.
    """
    match = _FENCE_RE.match(line)
    if match is None:
        return None
    if match.group("fence")[0] == "`" and "`" in match.group("info"):
        return None
    return match


def _starts_fence(text: str) -> bool:
    """Return True when *text* opens a fenced block."""
    return _fence_match(text) is not None


def _open_fence(line: str, containers: _ListContainers) -> _OpenFence | None:
    """Return the fence that *line* opens, or None when it opens nothing."""
    match = _fence_match(line)
    if match is None or containers.over_indented(match.group("indent")):
        return None
    fence = match.group("fence")
    return _OpenFence(char=fence[0], length=len(fence), indent=match.group("indent"))


def _closes(line: str, open_fence: _OpenFence, containers: _ListContainers) -> re.Match[str] | None:
    """Return the match when *line* is a closing candidate for *open_fence*.

    A candidate uses the same fence character and is at least as long as the
    opener. It is a VALID close when its info string is blank and a
    MALFORMED close when it is not; the caller distinguishes them.
    """
    match = _FENCE_RE.match(line)
    if match is None or containers.over_indented(match.group("indent")):
        return None
    fence = match.group("fence")
    if fence[0] != open_fence.char or len(fence) < open_fence.length:
        return None
    return match


def _scan_open(line: str, containers: _ListContainers) -> _OpenFence | None:
    """Return the fence *line* opens, advancing *containers* over the line.

    Sync before classifying: a dedent must close its container before the
    fence test reads the base, or a stale base accepts a marker CommonMark
    reads as indented code.
    """
    containers.sync(line)
    opened = _open_fence(line, containers)
    if opened is not None:
        containers.opened_fence()
        return opened
    return _open_fence_in_item(line, containers, containers.observe(line))


def _open_fence_in_item(
    line: str, containers: _ListContainers, column: int | None
) -> _OpenFence | None:
    """Return a fence opening in *line*'s list-item content, or None.

    CommonMark re-parses a marker line's remainder inside the item the marker
    just opened, so `- ``` ` opens a fenced block whose indent is the item's
    content column, and `- - ``` ` opens two items and then the block. Testing
    only the raw line missed those, and the real closing fence further down was
    then read as a fresh opener, so `--write` appended a fence to a document
    that was already well formed.
    """
    while column is not None:
        rest = line.expandtabs(4)[column:]
        if _is_blank(rest):
            return None
        # Keep whatever indentation is left after the content column. Five or
        # more columns of padding leave four behind, which makes the rest of
        # the line indented code rather than a block start; stripping it here
        # opened a fence in literal code and let `--write` fence it.
        nested = " " * column + rest
        opened = _open_fence(nested, containers)
        if opened is not None:
            containers.opened_fence()
            return opened
        deeper = containers.observe(nested)
        if deeper is None or deeper <= column:
            return None  # no further container; also guards against no progress
        column = deeper
    return None


@dataclass(frozen=True)
class _Line:
    """One source line and the terminator that followed it."""

    text: str
    sep: str


def _split_lines(content: str) -> list[_Line]:
    """Split *content* into lines that each carry their own terminator.

    Rejoining every text and sep reproduces *content* exactly, so a repair
    can never normalize a line ending, or delete a Unicode separator, that
    it did not set out to touch.
    """
    if not content:
        return []
    tokens = _LINE_SPLIT_RE.split(content)
    texts, seps = tokens[0::2], tokens[1::2]
    if texts and texts[-1] == "":
        texts.pop()  # content ended with a terminator; no empty final line
    return [_Line(text, seps[i] if i < len(seps) else "") for i, text in enumerate(texts)]


def _default_sep(lines: list[_Line]) -> str:
    """Return the terminator an inserted line should carry."""
    for line in lines:
        if line.sep:
            return line.sep
    return "\n"


def _join(lines: list[_Line]) -> str:
    return "".join(line.text + line.sep for line in lines)


def find_fence_defects(content: str) -> list[Defect]:
    """Return every fence defect in *content*, in file order."""
    lines = _split_lines(content)
    defects: list[Defect] = []
    open_fence: _OpenFence | None = None
    containers = _ListContainers()

    fence_base = 0
    for number, line in enumerate(lines, start=1):
        if open_fence is not None and _container_closed(line.text, fence_base):
            open_fence = None  # the item holding the block ended
        if open_fence is None:
            open_fence = _scan_open(line.text, containers)
            fence_base = containers.base() if open_fence is not None else 0
            continue

        match = _closes(line.text, open_fence, containers)
        if match is None:
            continue
        if _is_blank(match.group("info")):
            open_fence = None
            continue

        # Spaces and tabs only. A bare `rstrip()` also removes U+00A0 and
        # U+3000, which are exactly the characters that make this line
        # malformed, so the report rendered an invalid closer as a valid
        # looking bare fence and hid its own reason.
        defects.append(
            Defect(line=number, kind=MALFORMED_CLOSING, text=line.text.rstrip(" \t"))
        )
        # The malformed line opens the next block, mirroring the repair. When
        # it cannot open one (a backtick fence carrying a backtick in its info
        # string), the bare fence the repair emits above it has closed the
        # block and the line is now literal prose, so the state is None.
        # Keeping the stale opener here desynced report from reality and made
        # repair non-idempotent.
        open_fence = _scan_open(line.text, containers)
        fence_base = containers.base() if open_fence is not None else 0

    if open_fence is not None:
        defects.append(
            Defect(line=len(lines), kind=UNCLOSED_BLOCK, text=open_fence.closing.strip(" \t")),
        )
    return defects


def repair_markdown_fences(content: str) -> str:
    """Return *content* with every fence defect repaired.

    Idempotent: repairing already-repaired content returns it unchanged.
    """
    lines = _split_lines(content)
    default_sep = _default_sep(lines)
    result: list[_Line] = []
    open_fence: _OpenFence | None = None
    containers = _ListContainers()

    fence_base = 0
    for line in lines:
        if open_fence is not None and _container_closed(line.text, fence_base):
            open_fence = None  # the item holding the block ended
        if open_fence is None:
            result.append(line)
            open_fence = _scan_open(line.text, containers)
            fence_base = containers.base() if open_fence is not None else 0
            continue

        match = _closes(line.text, open_fence, containers)
        if match is None:
            result.append(line)
            continue
        if _is_blank(match.group("info")):
            result.append(line)
            open_fence = None
            continue

        result.append(_Line(open_fence.closing, line.sep or default_sep))
        result.append(line)
        open_fence = _scan_open(line.text, containers)
        fence_base = containers.base() if open_fence is not None else 0

    if open_fence is not None:
        if result and not result[-1].sep:
            # The file had no trailing terminator; the last line needs one
            # before a fence can sit on its own line after it.
            result[-1] = replace(result[-1], sep=default_sep)
            result.append(_Line(open_fence.closing, ""))
        else:
            result.append(_Line(open_fence.closing, default_sep))

    return _join(result)


def iter_markdown_files(paths: list[Path], pattern: str) -> list[Path]:
    """Expand *paths* into markdown files, skipping vendor and VCS trees."""
    found: list[Path] = []
    for path in paths:
        if path.is_file():
            found.append(path)
            continue
        for candidate in sorted(path.rglob(pattern)):
            if not candidate.is_file():
                continue
            if _SKIP_DIRS.intersection(candidate.parts):
                continue
            found.append(candidate)
    return found


def _report(results: dict[str, list[Defect]], *, as_json: bool, wrote: list[str]) -> None:
    if as_json:
        payload = {
            "files": {name: [asdict(d) for d in defects] for name, defects in results.items()},
            "defect_count": sum(len(d) for d in results.values()),
            "repaired": wrote,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    if not results:
        print("No fence defects found")
        return
    for name, defects in results.items():
        for defect in defects:
            print(f"{name}:{defect.line}: {defect.kind}: {defect.text}")
    total = sum(len(d) for d in results.values())
    print(f"\n{total} defect(s) in {len(results)} file(s)")
    if wrote:
        print(f"Repaired {len(wrote)} file(s)")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Detect and repair malformed markdown code fence closings",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Repair the defects in place (default: report only, exit 1 on findings)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    parser.add_argument("--pattern", default="*.md", help="Glob for directory scans")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in (args.paths or ["."])]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(f"Error: path does not exist: {', '.join(missing)}", file=sys.stderr)
        return 2

    results: dict[str, list[Defect]] = {}
    wrote: list[str] = []
    for file_path in iter_markdown_files(paths, args.pattern):
        try:
            raw = file_path.read_bytes()
            content = raw.decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Error: cannot read {file_path}: {exc}", file=sys.stderr)
            return 2

        defects = find_fence_defects(content)
        if not defects:
            continue
        results[str(file_path)] = defects

        if not args.write:
            continue
        bom = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
        try:
            file_path.write_bytes(bom + repair_markdown_fences(content).encode("utf-8"))
        except OSError as exc:
            print(f"Error: cannot write {file_path}: {exc}", file=sys.stderr)
            return 2
        wrote.append(str(file_path))

    _report(results, as_json=args.json, wrote=wrote)
    return 1 if (results and not args.write) else 0


if __name__ == "__main__":
    sys.exit(main())
