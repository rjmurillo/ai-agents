#!/usr/bin/env python3
# taste-lint: ignore file-size
# Over the 500-line ceiling. No exact total here: this comment adds lines to
# the file it measures, so the figure was already wrong when written. Roughly
# 150 lines are `_ListContainers`,
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
_MAX_LIST_PAD = 4


def _indent_width(text: str) -> int:
    """Return the column *text* occupies, tabs expanded to a 4-column stop."""
    return len(text.expandtabs(4))


def _container_closed(line: str, base: int) -> bool:
    """Return True when *line* dedents out of the container holding a block.

    A fenced block inside a list item ends when the document leaves that item,
    even without a closing marker. Tracking a block's lifetime independently of
    its container left the block open to EOF, so `--write` appended a closing
    fence to a document CommonMark already considers complete. A top-level
    block has base 0 and can never be closed this way.
    """
    if base == 0 or not line.strip():
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

    Rules 9 and 10 were both documented as deliberate limitations for one
    commit, on the reasoning that each only made the scanners miss a fence,
    which is the safe direction for a tool that writes files. That reasoning
    was wrong twice. Both instead left a block open past its real end, so
    `--write` appended a closing fence to documents CommonMark already
    considers complete. `- - ``` ` was additionally a regression from this
    module's own container work, since the flat scanner never opened a
    container there at all. Prefer measuring a failure's direction over
    reasoning about it.
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
        if not line.strip():
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
        if not line.strip():
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
        empty = not match.group("rest").strip()
        if self._in_paragraph and (empty or (number is not None and int(number) != 1)):
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
        if not rest.strip():
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
        if not match.group("info").strip():
            open_fence = None
            continue

        defects.append(Defect(line=number, kind=MALFORMED_CLOSING, text=line.text.rstrip()))
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
            Defect(line=len(lines), kind=UNCLOSED_BLOCK, text=open_fence.closing.strip()),
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
        if not match.group("info").strip():
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
