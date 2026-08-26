#!/usr/bin/env python3
# taste-lint: ignore file-size
# Over the 500-line ceiling. This comment previously named an exact total, 504,
# which was true when written and never re-measured; the replacement figure was
# stale before the commit landed, because the comment adds lines to the file it
# measures. So no total is quoted. Roughly 150 lines are `_ListContainers`,
# duplicated byte-for-byte in fix-markdown-fences because the two skills ship
# as separate plugin directories and neither is on the other's import path.
# The real fix is to move that class to the plugin's shared lib, which both
# skills can already reach through the ADR-047 inline bootstrap; that is a
# change to two skills' vendoring surface, so it is not being made inside a
# review round on an unrelated fix. The cheap reductions here are already
# taken (the module docstring no longer restates SKILL.md, the repeated
# finding notes are keyed by kind, and main() is split into
# _resolve_banned_words and _emit_json). Scoped to file-size only; complexity
# and every other rule still apply.
"""Deterministic Layer 1 and Layer 2 checks for the prose-self-check skill.

Both layers are pattern matches over text that the agent used to run by eye.
SKILL.md is the reference for what each layer covers and why; this module is
the engine. Layer 3 stays in `burstiness.py`, Layer 4 stays with the agent.

The banned-word list is parsed from the voice rule at runtime, never copied
here. Every run reports what it examined, not only what it found: a document
whose unterminated fence hid most of its prose must not read as clean.

EXIT CODES (ADR-035):
  0 - No high-severity findings. Info findings may still be present.
  1 - At least one high-severity finding.
  2 - Configuration error: a named file does not exist or cannot be read.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HIGH = "high"
INFO = "info"

UNTERMINATED_FENCE = "unterminated_fence"

# Written as escapes, not literals: this file ships in the plugin tree,
# where the dash ban is enforced at the byte level (Issue #4079).
EM_DASH = "\u2014"
EN_DASH = "\u2013"

# Tiering from SKILL.md Layer 1. These words top keyword scans but are
# ~0% reader-cited, so presence alone is not a finding.
LOW_SIGNAL_WORDS = frozenset(
    {"however", "thus", "moreover", "additionally", "nuanced", "comprehensive"},
)

# Where the voice rule can live, in resolution order. The plugin ships the
# rule under its own root; a consumer checkout has one of the two mirrors.
_RULE_CANDIDATES: tuple[tuple[str | None, str], ...] = (
    ("CLAUDE_PLUGIN_ROOT", "rules/voice.md"),
    ("COPILOT_PLUGIN_ROOT", "instructions/voice.instructions.md"),
    (None, ".claude/rules/voice.md"),
    (None, ".github/instructions/voice.instructions.md"),
)
_PLUGIN_MARKER = Path(".claude-plugin") / "plugin.json"

_BANNED_HEADING = re.compile(r"^#{1,6}\s+Banned Vocabulary\s*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_CODE_TOKEN = re.compile(r"`([^`]+)`")
_WORD_ONLY = re.compile(r"^[a-z][a-z'-]*$")
_TOKEN = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
# A token touching one of these is part of a URL slug, an identifier, or
# a tag, not prose. `robust` inside `https://x.com/robust` is not a word
# choice anyone can rewrite.
_NON_PROSE_NEIGHBORS = frozenset("/_>=\\")

_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
# CommonMark caps a fence marker at three spaces of indent; past that it is
# an indented code block and the backticks are literal content. Without the
# cap a literal marker inside an indented block started masking and hid the
# prose after it. The cap is measured from the innermost open list item, not
# from column zero; `_ListContainers` below carries the four rules that decide
# where that item's content column sits.
#
# Same bound as the sibling fence scanner, which ships in the same plugin
# root and is quoted here rather than imported, because the two skills ship
# as separate directories and neither is on the other's import path.
#
# `skills/fix-markdown-fences/scripts/fix_fences.py` lines 234-236, verbatim:
#
#     def over_indented(self, indent: str) -> bool:
#         """Return True when *indent* puts the marker inside an indented code block."""
#         return _indent_width(indent) - self._base() > _MAX_FENCE_INDENT
#
# `test_sibling_bound_quote_matches_its_source` pins both the quote and the
# line range against that file, so the claim fails a test rather than a
# review round when either side moves.
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


def _fence_match(line: str) -> re.Match[str] | None:
    """Return the match when *line* is a fence opener, ignoring its indent.

    CommonMark: a backtick opening fence may not carry a backtick in its info
    string, which is what keeps ``a ``` b`` from opening a block. This module
    matched the raw pattern at every opener and so accepted those, ending the
    paragraph and masking the prose after it. Every opener path goes through
    here now.
    """
    match = _FENCE.match(line)
    if match is None:
        return None
    if match.group("fence")[0] == "`" and "`" in match.group("info"):
        return None
    return match


def _starts_fence(text: str) -> bool:
    """Return True when *text* opens a fenced block."""
    return _fence_match(text) is not None


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
    13. An ordered marker is ASCII digits only. Python's regex `d`
        shorthand also matches Unicode decimal digits, so a line led by
        U+0661 ARABIC-INDIC DIGIT ONE opened a list here while CommonMark
        read it as a paragraph.
    14. Blank means spaces and tabs, not `str.strip()`. Unicode whitespace
        made a line holding one U+00A0 look blank, which left a container
        open past its item, and made `-` plus U+00A0 look like an empty item
        when CommonMark reads it as paragraph text. See `_is_blank`.

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
    unclosed, so the writes are correct. The cost is confined to missed
    detections here and to blockquote code reaching the prose checks in the
    sibling scanner. Four such markers exist in this repository, in two
    archived session logs, and they are the whole of the remaining
    under-masking. Closing it means consuming line prefixes through the entire
    scan rather than reasoning in columns, which is a larger change than any
    rule above.
    """

    __slots__ = ("_columns", "_in_paragraph", "_item_still_empty")

    def __init__(self) -> None:
        self._columns: list[int] = []
        self._in_paragraph = False
        self._item_still_empty = False

    def over_indented(self, indent: str) -> bool:
        """Return True when *indent* puts the marker inside an indented code block."""
        return _indent_width(indent) - self._base() > _MAX_FENCE_INDENT

    def sync(self, line: str) -> None:
        """Close containers that *line* has dedented out of."""
        if _is_blank(line):
            self._in_paragraph = False  # a blank line ends any open paragraph
            if self._item_still_empty and self._columns:
                # Rule 8: an item may begin with at most one blank line, so a
                # blank directly after an empty marker closes it. Without this
                # the stale column made the next indented block look list-nested,
                # and `--write` would then fence literal indented code.
                self._columns.pop()
                self._item_still_empty = False
            return
        if self._in_paragraph and not self._starts_a_block(line):
            return  # rule 6: a lazy continuation keeps its container open
        width = _indent_width(line[: len(line) - len(line.lstrip(" \t"))])
        while self._columns and width < self._columns[-1]:
            self._columns.pop()
            self._in_paragraph = False  # rule 15: it closed with the item

    def opened_fence(self) -> None:
        """Record that a fenced block opened on this line."""
        self._in_paragraph = False  # rule 7: a fence ends the paragraph
        self._item_still_empty = False  # the fence is the item's content

    def observe(self, line: str) -> int | None:
        """Open a container when *line* starts a list item, then track paragraphs.

        Returns the content column it opened, so the caller can re-scan the
        rest of the line against it. CommonMark re-parses a marker line's
        remainder inside the item the marker just opened, which is how
        `- ``` ` opens a fenced block and `- - a` opens two items.
        """
        if _is_blank(line):
            return None  # `sync` already ended the paragraph
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
            return column
        self._item_still_empty = False  # this line is the item's first content
        content = self._relative(line)
        body = content.lstrip(" ")
        if len(content) - len(body) > _MAX_FENCE_INDENT:
            # Indented code when no paragraph is open, a lazy continuation when
            # one is. Neither changes the state, and both differ from prose.
            return None
        self._in_paragraph = not (
            _ATX_HEADING.match(body)
            or _THEMATIC_BREAK.match(body)
            or _starts_fence(body)
            or _BLOCK_QUOTE.match(body)
            or (self._in_paragraph and _SETEXT_UNDERLINE.match(body))
        )
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


# A code span may wrap one line but never spans a paragraph break. With
# DOTALL and no bound, two stray backticks paragraphs apart paired and
# blanked everything between them, so a run could miss an em dash and
# still exit 0.
_INLINE_CODE = re.compile(r"`(?:[^`\n]|\n(?!\n))*`")

# Layer 2 structural tells. Each pattern targets one shape SKILL.md names.
# A clause gap may cross one hard wrap but never a paragraph break, so a tell
# in prose wrapped near 80 columns is still seen.
_GAP = r"(?:[^,.;:|\n]|\n(?!\n)){1,60}"
# The comma may be followed by one hard wrap, never a paragraph break.
_WRAP = r",[ \t]*(?:\n(?!\n)[ \t]*)?"

_NOTES = {
    "contrast_framing": "contrast framing; state the claim directly",
    "trailing_offer": "manufactured trailing offer; delete it",
    "signposting": "signposting opener; lead with the point",
    "model_identity": "model-identity phrase; remove it",
}

_STRUCTURAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "contrast_framing",
        # The subject is any short noun phrase, not just a pronoun. SKILL.md
        # documents the shape as "not X, it's Y"; anchoring on it/this/that
        # missed every sentence with a real subject.
        re.compile(
            r"\b[A-Za-z][\w'-]*(?:\s+[\w'-]+){0,3}\s+"
            r"(?:is|was|are|were)n?(?:'t| not)\s+(?:just\s+)?"
            + _GAP
            + _WRAP
            + r"(?:it|this|that|they)(?:'s|'re| is| are)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "contrast_framing",
        re.compile(
            r"\b(?:is|are)n(?:'|)t about "
            + _GAP
            + _WRAP
            + r"(?:it|they)(?:'s|'re| is| are) about\b",
            re.IGNORECASE,
        ),
    ),
    (
        "contrast_framing",
        # `rather` is mandatory: "not X, but rather Y" is the contrast tell,
        # while "not X, but Y" is ordinary English and fired on 97 of 103
        # corpus matches, this repo's own rule files among them.
        re.compile(r"\bnot " + _GAP + _WRAP + r"but rather\b", re.IGNORECASE),
    ),
    (
        "trailing_offer",
        re.compile(
            r"\b(?:want me to|would you like me to|i could also|let me know if you'd like"
            r"|shall i also)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "signposting",
        re.compile(
            r"(?:^|\n)\s*(?:>\s*|[-*+]\s+|\d+\.\s+)?"
            r"(?:Honestly,|Look,|Let's dive in|It's worth noting that|In today's landscape)",
        ),
    ),
    (
        "model_identity",
        re.compile(
            r"\bas an AI(?: language model| assistant)?\b|\bI'm just an AI\b", re.IGNORECASE
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    """One prose tell located in an artifact."""

    line: int
    column: int
    kind: str
    severity: str
    match: str
    note: str


def _plugin_install_root() -> Path | None:
    """Return the plugin root discovered by walking up from this file."""
    current = Path(__file__).resolve().parent
    while True:
        if (current / _PLUGIN_MARKER).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def discover_rules_file() -> Path | None:
    """Return the voice rule file, or None when no copy is reachable."""
    for env_var, relpath in _RULE_CANDIDATES:
        if env_var is None:
            candidate = Path.cwd() / relpath
        else:
            root = os.environ.get(env_var)
            if not root:
                continue
            candidate = Path(root) / relpath
        if candidate.is_file():
            return candidate

    install_root = _plugin_install_root()
    if install_root is None:
        return None
    for relpath in ("rules/voice.md", "instructions/voice.instructions.md"):
        candidate = install_root / relpath
        if candidate.is_file():
            return candidate
    return None


def parse_banned_words(rules_text: str) -> set[str]:
    """Return the backticked tokens under the "Banned Vocabulary" heading.

    Stops at the next heading so the replacement examples below the list
    are not mistaken for entries.
    """
    heading = _BANNED_HEADING.search(rules_text)
    if heading is None:
        return set()
    body_start = heading.end()
    following = _NEXT_HEADING.search(rules_text, body_start)
    body = rules_text[body_start : following.start() if following else len(rules_text)]
    return {
        token.lower()
        for token in _CODE_TOKEN.findall(body)
        if _WORD_ONLY.match(token.strip().lower())
    }


def _fence_in_item(
    line: str, containers: _ListContainers, column: int | None
) -> re.Match[str] | None:
    """Return a fence opening in *line*'s list-item content, or None.

    CommonMark re-parses a marker line's remainder inside the item the marker
    just opened, so `- ~~~` opens a fenced block and `- - ~~~` opens two items
    and then the block. Testing only the raw line left that code body exposed
    to the prose checks and made the real closing marker look like a new
    opener.
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
        match = _fence_match(nested)
        if match is not None and not containers.over_indented(match.group("indent")):
            return match
        deeper = containers.observe(nested)
        if deeper is None or deeper <= column:
            return None  # no further container; also guards against no progress
        column = deeper
    return None

def _blank_fenced_blocks(text: str) -> tuple[list[str], int | None]:
    """Return the lines of *text* with every fenced code block blanked out.

    Blanking rather than dropping keeps line numbers aligned, and the fence
    markers go too so their backticks cannot pair with an inline span. Also
    returns the line of a fence still open at EOF; everything after it went
    unscanned.
    """
    lines: list[str] = []
    fence: str | None = None
    opened_at: int | None = None
    containers = _ListContainers()
    fence_base = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if fence is not None and _container_closed(line, fence_base):
            fence = None  # the item holding the block ended
            opened_at = None
        if fence is None:
            # Sync before classifying: a dedent must close its container
            # before the fence test reads the base.
            containers.sync(line)
        match = _fence_match(line)
        if match is not None and containers.over_indented(match.group("indent")):
            match = None
        if fence is None:
            if match is None:
                match = _fence_in_item(line, containers, containers.observe(line))
                if match is None:
                    lines.append(line)
                    continue
            containers.opened_fence()
            fence = match.group("fence")
            fence_base = containers.base()
            opened_at = number
            lines.append("")
            continue
        lines.append("")
        # CommonMark: a closing fence carries no info string. Accepting one
        # inverted open and close for the rest of the document, so fenced
        # code was linted as prose and real prose was silently skipped.
        if (
            match is not None
            and match.group("fence")[0] == fence[0]
            and len(match.group("fence")) >= len(fence)
            and not match.group("info").strip()
        ):
            fence = None
            opened_at = None
    return lines, opened_at


def _mask_inline_code(text: str) -> str:
    """Blank out inline code spans, preserving every column and newline.

    Runs over the whole document: masking line by line pairs the wrong
    backticks on a wrapped span and leaves quoted examples exposed.
    """
    return _INLINE_CODE.sub(
        lambda m: "".join(c if c == "\n" else " " for c in m.group(0)),
        text,
    )


@dataclass(frozen=True)
class Scan:
    """The result of one artifact scan, with the coverage behind it."""

    findings: list[Finding]
    examined: int
    total: int
    unterminated_fence_line: int | None


def _prose_lines(text: str) -> tuple[list[tuple[int, str]], str, int, int | None]:
    """Return prose lines, the masked document, the source line count, and
    any fence still open at EOF."""
    blanked, opened_at = _blank_fenced_blocks(text)
    masked = _mask_inline_code("\n".join(blanked))
    lines = [
        (number, line) for number, line in enumerate(masked.split("\n"), start=1) if line.strip()
    ]
    return lines, masked, len(blanked), opened_at


def _lexical_findings(lines: list[tuple[int, str]], banned: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in lines:
        for dash, name in ((EM_DASH, "em_dash"), (EN_DASH, "en_dash")):
            start = line.find(dash)
            while start != -1:
                findings.append(
                    Finding(
                        line=number,
                        column=start + 1,
                        kind=name,
                        severity=HIGH,
                        match=dash,
                        note="banned by the universal rule; restructure or use a comma",
                    ),
                )
                start = line.find(dash, start + 1)
        for match in _TOKEN.finditer(line):
            before = line[match.start() - 1] if match.start() else ""
            after = line[match.end()] if match.end() < len(line) else ""
            if before in _NON_PROSE_NEIGHBORS or after in _NON_PROSE_NEIGHBORS:
                continue
            word = match.group(0).lower()
            if word.endswith("'s"):
                word = word[:-2]
            # A hyphenated compound still uses the word it is built from, so
            # `landscape-level` counts as `landscape`.
            parts = {word, *(p for p in re.split(r"[-']", word) if p)}
            hits = parts & banned
            if not hits:
                continue
            low = hits <= LOW_SIGNAL_WORDS
            findings.append(
                Finding(
                    line=number,
                    column=match.start() + 1,
                    kind="banned_word_low_signal" if low else "banned_word",
                    severity=INFO if low else HIGH,
                    match=match.group(0),
                    note=(
                        "low-signal; cut only if this paragraph also fails Layer 4"
                        if low
                        else "banned vocabulary; be specific instead"
                    ),
                ),
            )
    return findings


def _locate(offset: int, starts: list[int]) -> tuple[int, int]:
    """Map a document offset to a 1-indexed (line, column)."""
    index = bisect.bisect_right(starts, offset) - 1
    return index + 1, offset - starts[index] + 1


def _structural_findings(masked: str) -> list[Finding]:
    """Find Layer 2 tells across the whole masked document.

    Matching per line missed every tell straddling a hard wrap, the common
    case in prose wrapped near 80 columns.
    """
    starts = [0]
    for index, char in enumerate(masked):
        if char == "\n":
            starts.append(index + 1)

    findings: list[Finding] = []
    for kind, pattern in _STRUCTURAL_PATTERNS:
        for match in pattern.finditer(masked):
            offset = match.start()
            # A pattern anchored on (?:^|\n) consumes the newline itself.
            if match.group(0).startswith("\n"):
                offset += 1
            line, column = _locate(offset, starts)
            findings.append(
                Finding(
                    line=line,
                    column=column,
                    kind=kind,
                    severity=HIGH,
                    match=" ".join(match.group(0).split()),
                    note=_NOTES[kind],
                ),
            )
    return findings


def scan_prose(text: str, banned: set[str]) -> Scan:
    """Scan *text* and report both the findings and the coverage behind them.

    A run that read almost nothing must not look like a clean one, so the
    caller also gets the coverage (`.claude/rules/ci-scripts.md` MUST-12).
    """
    lines, masked, total, opened_at = _prose_lines(text)
    findings = _lexical_findings(lines, banned) + _structural_findings(masked)
    if opened_at is not None:
        findings.append(
            Finding(
                line=opened_at,
                column=1,
                kind=UNTERMINATED_FENCE,
                severity=HIGH,
                match="",
                note=(
                    f"fence never closes; lines {opened_at} to EOF went "
                    "unscanned, so this run cannot clear Layers 1-2"
                ),
            ),
        )
    return Scan(
        findings=sorted(findings, key=lambda f: (f.line, f.column, f.kind)),
        examined=len(lines),
        total=total,
        unterminated_fence_line=opened_at,
    )


def lint_prose(text: str, banned: set[str]) -> list[Finding]:
    """Return every Layer 1 and Layer 2 finding in *text*, in file order."""
    return scan_prose(text, banned).findings


def _read(name: str) -> str:
    """Read an artifact, dropping a UTF-8 BOM.

    A surviving U+FEFF sits before a first-line fence and defeats the
    `^[ \t]*` anchor, so the opener goes unrecognized, the block body is
    linted as prose, and the real closer is read as an opener. The sibling
    fence script decodes the same way; the two must agree. `sys.stdin.read`
    does not honor `utf-8-sig`, so that branch strips the character itself.
    """
    if name == "-":
        return sys.stdin.read().lstrip("\ufeff")
    return Path(name).read_text(encoding="utf-8-sig")


def _emit_text(results: dict[str, Scan], rules_note: str | None) -> None:
    if rules_note:
        print(rules_note, file=sys.stderr)
    total_high = 0
    for name, scan in results.items():
        for finding in scan.findings:
            total_high += finding.severity == HIGH
            print(
                f"{name}:{finding.line}:{finding.column}: {finding.severity}: "
                f"{finding.kind}: {finding.match!r} ({finding.note})",
            )
    examined = sum(scan.examined for scan in results.values())
    source = sum(scan.total for scan in results.values())
    total = sum(len(scan.findings) for scan in results.values())
    # Name what was read, not just the verdict: a run that scanned almost
    # nothing must not read as a clean one.
    coverage = f"{examined} prose line(s) of {source} in {len(results)} file(s)"
    if not total:
        print(f"Layers 1-2 clean: 0 findings in {coverage}.")
    else:
        print(f"\n{total} finding(s), {total_high} high severity, in {coverage}")
    print("Layer 4 (emptiness gate) is still yours to run.")


def _resolve_banned_words(
    rules_arg: str | None,
) -> tuple[set[str], Path | None, str | None] | None:
    """Load the banned-word list, or None when the rules file is unreadable.

    A missing rule degrades to the dash and structural checks; only an
    unreadable one is an error.
    """
    rules_path = Path(rules_arg) if rules_arg else discover_rules_file()
    if rules_path is None:
        return (
            set(),
            None,
            (
                "Warning: no voice rule found; running dash and structural checks only. "
                "Pass --rules PATH to enable the banned-word check."
            ),
        )
    try:
        banned = parse_banned_words(rules_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Error: cannot read rules file {rules_path}: {exc}", file=sys.stderr)
        return None
    if not banned:
        return (
            banned,
            rules_path,
            (
                f"Warning: no 'Banned Vocabulary' section in {rules_path}; "
                "running dash and structural checks only."
            ),
        )
    return banned, rules_path, None


def _emit_json(results: dict[str, Scan], rules_path: Path | None, banned: set[str]) -> None:
    """Print the machine-readable report."""
    print(
        json.dumps(
            {
                "rules_file": str(rules_path) if rules_path else None,
                "banned_word_count": len(banned),
                "files": {
                    name: {
                        "findings": [asdict(f) for f in scan.findings],
                        "examined_lines": scan.examined,
                        "source_lines": scan.total,
                        "unterminated_fence_line": scan.unterminated_fence_line,
                    }
                    for name, scan in results.items()
                },
                "high_severity_count": sum(
                    1 for scan in results.values() for f in scan.findings if f.severity == HIGH
                ),
            },
            indent=2,
            sort_keys=True,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Run prose-self-check Layers 1 and 2 over an artifact",
    )
    parser.add_argument("files", nargs="+", help="Files to check, or - for stdin")
    parser.add_argument("--rules", help="Path to the voice rule (default: auto-discover)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    args = parser.parse_args(argv)

    resolved = _resolve_banned_words(args.rules)
    if resolved is None:
        return 2
    banned, rules_path, rules_note = resolved

    results: dict[str, Scan] = {}
    for name in args.files:
        try:
            text = _read(name)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Error: cannot read {name}: {exc}", file=sys.stderr)
            return 2
        results[name] = scan_prose(text, banned)

    if args.json:
        # The warning is the only signal that the banned-word scan was
        # disabled; dropping it in JSON mode made that silent.
        if rules_note:
            print(rules_note, file=sys.stderr)
        _emit_json(results, rules_path, banned)
    else:
        _emit_text(results, rules_note)

    return 1 if any(f.severity == HIGH for s in results.values() for f in s.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
