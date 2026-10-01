# taste-lint: ignore file-size, one 500-line class; the container model reads as a whole.
"""CommonMark container model (list items) shared by two skill scripts.

`ListContainers` tracks the content column of the innermost open list item,
line by line. `fix-markdown-fences` and `prose-self-check` both use it to decide
whether a fence marker is indented too far to be a fence. One copy lives here so
a defect fixed once is fixed for both (issue #5352).

Import-self-contained: standard library plus the sibling `commonmark_links`.
"""

from __future__ import annotations

import re

from .commonmark_links import (
    LINK_LABEL_ONLY,
    LINK_TITLE_ONLY,
    bare_title,
    label_opens,
    link_reference,
    link_tail,
)

# A fence opener. Shared by the two skills because `ListContainers` asks whether a
# line starts a fence when it decides whether a list item ends.
FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


def fence_match(line: str) -> re.Match[str] | None:
    """Return the match when *line* is a fence opener, ignoring its indent.

    CommonMark: a backtick opening fence may not carry a backtick in its info
    string, which is what keeps ``a ``` b`` from opening a block. Every opener
    path goes through here so none of them can forget that rule.
    """
    match = FENCE_RE.match(line)
    if match is None:
        return None
    if match.group("fence")[0] == "`" and "`" in match.group("info"):
        return None
    return match


def starts_fence(text: str) -> bool:
    """Return True when *text* opens a fenced block."""
    return fence_match(text) is not None


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


_MAX_LIST_PAD = 4


def _indent_width(text: str) -> int:
    """Return the column *text* occupies, tabs expanded to a 4-column stop."""
    return len(text.expandtabs(4))


def is_blank(text: str) -> bool:
    """Return True when *text* is empty or only spaces and tabs.

    Not `str.strip()`, which also removes U+00A0 and the rest of Unicode
    whitespace. CommonMark counts only spaces and tabs, so `-\u00a0` is
    paragraph text rather than an empty list item, and a line holding one
    non-breaking space is content rather than a blank that leaves a container
    open.
    """
    return not text.strip(" \t")

def container_closed(line: str, base: int) -> bool:
    """Return True when *line* dedents out of the container holding a block.

    A fenced block inside a list item ends when the document leaves that item,
    even without a closing marker. Tracking a block's lifetime independently of
    its container left the block open to EOF, so `--write` appended a closing
    fence to a document CommonMark already considers complete. A top-level
    block has base 0 and can never be closed this way.
    """
    if base == 0 or is_blank(line):
        return False
    return _indent_width(line[: len(line) - len(line.lstrip(" \t"))]) < base


class ListContainers:
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
        See `container_closed`.
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
        when CommonMark reads it as paragraph text. See `is_blank`.
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
        if is_blank(line):
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
        result = link_tail(tail, 0)
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
        if is_blank(line):
            return None  # `sync` already ended the paragraph
        if self._open_label_blank is not None:
            if not self._ends_an_open_label(line):
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
            self._awaiting_link_destination and link_tail(body, 0) is not None
        ) or (self._awaiting_link_title and bool(LINK_TITLE_ONLY.match(body)))
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
        definition = None if self._in_paragraph else link_reference(body)
        dest_line = link_tail(body, 0) if self._awaiting_link_destination else None
        title_line = bare_title(body) if self._awaiting_link_title else None
        label_only = not self._in_paragraph and bool(LINK_LABEL_ONLY.match(body))
        opens_label = not self._in_paragraph and label_opens(body)
        self._in_paragraph = not (
            _ATX_HEADING.match(body)
            or _THEMATIC_BREAK.match(body)
            or starts_fence(body)
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
        self._open_label_blank = not body[1:].strip() if opens_label else None
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
            starts_fence(body)
            or _BLOCK_QUOTE.match(body)
            or _ATX_HEADING.match(body)
            or _THEMATIC_BREAK.match(body)
            or self._list_item(line) is not None
        )

    def _ends_an_open_label(self, line: str) -> bool:
        """Whether *line* ends a link label that opened on an earlier line.

        Not the same question as `_starts_a_block`, and the gap between the
        two was two separate `--write` corruptions.

        A setext underline is not a block start, so `_starts_a_block` is right
        to omit it, but `observe` already ends a paragraph on one and the
        reference parser stops a label there too. Without this clause the `=`
        in `[` / `=` / `2. ``` ` / `   ``` ` was swallowed as label text, the
        paragraph never closed, rule 4 vetoed the `2.`, the item's fence never
        opened, and its real closing fence became a fresh opener that `--write`
        then closed by appending to a balanced document. `=` of any length and
        `-` runs of one or two did this; `---` did not, because a thematic
        break is already a block start.

        Rule 4's veto must not apply here either. It asks whether a marker can
        INTERRUPT a paragraph, which an empty bullet or an ordered marker other
        than 1 cannot. The reference parser stops an open label at such a line
        regardless, so asking the interrupt question let `[` / `*` / `]:a` /
        `2. ``` ` complete a definition CommonMark never recognises. The veto
        reads `self._in_paragraph`, which is always True while a label is open,
        so the caller was deciding this line under the opposite assumption to
        the one it applies one statement later.
        """
        if self._starts_a_block(line):
            return True
        content = self._relative(line)
        body = content.lstrip(" ")
        if len(content) - len(body) > _MAX_FENCE_INDENT:
            return False  # rule 1: indented code, and it continues the label
        if _SETEXT_UNDERLINE.match(body):
            return True
        return self._list_item(line, interrupting=False) is not None

    def _list_item(
        self, line: str, *, interrupting: bool | None = None
    ) -> tuple[int, bool] | None:
        """Return *line*'s content column and whether its item has content.

        None when the line opens no list item. Returning both from the one
        match keeps the caller from re-matching a pattern that has already
        been shown to apply.

        *interrupting* overrides the paragraph state rule 4's veto is read
        against. It exists for one caller, `_ends_an_open_label`, which needs
        rules 1, 2, 3 and 5 without rule 4; duplicating the marker grammar
        there instead would add a fourth copy of it to keep in step.
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
        empty = is_blank(match.group("rest"))
        blocked = empty or (number is not None and int(number) != 1)
        in_paragraph = self._in_paragraph if interrupting is None else interrupting
        if in_paragraph and blocked and not self._outdents(match.group("indent")):
            return None  # rule 4: this marker cannot interrupt a paragraph
        if empty:
            return marker_end + 1, False  # rule 3
        pad = _indent_width(match.group("indent") + marker + match.group("pad")) - marker_end
        if pad == 0:
            return None  # a marker needs whitespace before its content
        return marker_end + (1 if pad > _MAX_LIST_PAD else pad), True  # rule 2
