#!/usr/bin/env python3
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


_LIST_MARKER = re.compile(r"^(?P<indent>[ \t]*)(?P<bullet>[-*+]|\d{1,9}[.)])(?P<pad>[ \t]+)")


def _indent_width(text: str) -> int:
    """Return the column *text* occupies, tabs expanded to a 4-column stop."""
    return len(text.expandtabs(4))


class _ListContainers:
    """The content column of the innermost open list item, tracked line by line.

    CommonMark measures a fence marker's indent from its containing block, not
    from column zero, so a marker four spaces deep inside a list item opens a
    fence while the identical line at top level is indented code. Measuring
    from column zero misreads the first as the second, so the whole block goes
    unseen and a defect inside it is never reported. Measured over the 4,531
    tracked Markdown files at this commit: of the 50 markers indented four or
    more spaces from column zero, 46 across 10 files are valid fences relative
    to their list item, among them `docs/codeql-rollout-checklist.md` and the
    shipped `ship` skill.

    Feed lines in order, and ask `over_indented` about a line BEFORE feeding
    it. Do not feed lines inside a fenced block: CommonMark does not read list
    markers there, and feeding them can only raise the base, which would widen
    what counts as a fence.
    """

    __slots__ = ("_columns",)

    def __init__(self) -> None:
        self._columns: list[int] = []

    def over_indented(self, indent: str) -> bool:
        """Return True when *indent* puts the marker inside an indented code block."""
        base = self._columns[-1] if self._columns else 0
        return _indent_width(indent) - base > _MAX_FENCE_INDENT

    def feed(self, line: str) -> None:
        """Update the open-container stack with one line of prose."""
        if not line.strip():
            return  # a blank line never closes a list item
        width = _indent_width(line[: len(line) - len(line.lstrip(" \t"))])
        while self._columns and width < self._columns[-1]:
            self._columns.pop()
        match = _LIST_MARKER.match(line)
        if match is not None:
            marker = match.group("indent") + match.group("bullet") + match.group("pad")
            self._columns.append(_indent_width(marker))


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


def _open_fence(line: str, containers: _ListContainers) -> _OpenFence | None:
    """Return the fence that *line* opens, or None when it opens nothing."""
    match = _FENCE_RE.match(line)
    if match is None or containers.over_indented(match.group("indent")):
        return None
    fence = match.group("fence")
    # CommonMark: a backtick opening fence may not carry a backtick in its
    # info string, which is what keeps ``a ``` b`` from opening a block.
    if fence[0] == "`" and "`" in match.group("info"):
        return None
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
    """Return the fence *line* opens, feeding *containers* when it opens none."""
    opened = _open_fence(line, containers)
    if opened is None:
        containers.feed(line)
    return opened


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

    for number, line in enumerate(lines, start=1):
        if open_fence is None:
            open_fence = _scan_open(line.text, containers)
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

    for line in lines:
        if open_fence is None:
            result.append(line)
            open_fence = _scan_open(line.text, containers)
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
