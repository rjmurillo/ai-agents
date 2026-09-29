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
import os
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "hook_utilities")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from hook_utilities.commonmark_containers import (  # noqa: E402
    FENCE_RE,
    ListContainers,
    container_closed,
    fence_match,
    is_blank,
)

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


def _open_fence(line: str, containers: ListContainers) -> _OpenFence | None:
    """Return the fence that *line* opens, or None when it opens nothing."""
    match = fence_match(line)
    if match is None or containers.over_indented(match.group("indent")):
        return None
    fence = match.group("fence")
    return _OpenFence(char=fence[0], length=len(fence), indent=match.group("indent"))


def _closes(line: str, open_fence: _OpenFence, containers: ListContainers) -> re.Match[str] | None:
    """Return the match when *line* is a closing candidate for *open_fence*.

    A candidate uses the same fence character and is at least as long as the
    opener. It is a VALID close when its info string is blank and a
    MALFORMED close when it is not; the caller distinguishes them.
    """
    match = FENCE_RE.match(line)
    if match is None or containers.over_indented(match.group("indent")):
        return None
    fence = match.group("fence")
    if fence[0] != open_fence.char or len(fence) < open_fence.length:
        return None
    return match


def _scan_open(line: str, containers: ListContainers) -> _OpenFence | None:
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
    line: str, containers: ListContainers, column: int | None
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
        if is_blank(rest):
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
    containers = ListContainers()

    fence_base = 0
    for number, line in enumerate(lines, start=1):
        if open_fence is not None and container_closed(line.text, fence_base):
            open_fence = None  # the item holding the block ended
        if open_fence is None:
            open_fence = _scan_open(line.text, containers)
            fence_base = containers.base() if open_fence is not None else 0
            continue

        match = _closes(line.text, open_fence, containers)
        if match is None:
            continue
        if is_blank(match.group("info")):
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
    containers = ListContainers()

    fence_base = 0
    for line in lines:
        if open_fence is not None and container_closed(line.text, fence_base):
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
        if is_blank(match.group("info")):
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
            # Report before aborting. `--write` may already have repaired
            # files on disk, and exiting straight to 2 left the caller with an
            # error on stderr, nothing on stdout, and no way to learn which
            # files had changed. In `--json` mode that meant empty stdout, so
            # a programmatic caller could not reconcile its own state either.
            # The writes that happened were correct; only the record was lost.
            _report(results, as_json=args.json, wrote=wrote)
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
            _report(results, as_json=args.json, wrote=wrote)  # same reason as above
            return 2
        wrote.append(str(file_path))

    _report(results, as_json=args.json, wrote=wrote)
    return 1 if (results and not args.write) else 0


if __name__ == "__main__":
    sys.exit(main())
