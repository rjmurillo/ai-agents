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
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Fence openers may be indented. CommonMark caps a fence indent at three
# spaces, but fences nested in list items routinely sit deeper in real
# documents, and this skill's job is repairing real documents.
_FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

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


def _open_fence(line: str) -> _OpenFence | None:
    """Return the fence that *line* opens, or None when it opens nothing."""
    match = _FENCE_RE.match(line)
    if match is None:
        return None
    fence = match.group("fence")
    # CommonMark: a backtick opening fence may not carry a backtick in its
    # info string, which is what keeps ``a ``` b`` from opening a block.
    if fence[0] == "`" and "`" in match.group("info"):
        return None
    return _OpenFence(char=fence[0], length=len(fence), indent=match.group("indent"))


def _closes(line: str, open_fence: _OpenFence) -> re.Match[str] | None:
    """Return the match when *line* is a closing candidate for *open_fence*.

    A candidate uses the same fence character and is at least as long as the
    opener. It is a VALID close when its info string is blank and a
    MALFORMED close when it is not; the caller distinguishes them.
    """
    match = _FENCE_RE.match(line)
    if match is None:
        return None
    fence = match.group("fence")
    if fence[0] != open_fence.char or len(fence) < open_fence.length:
        return None
    return match


def _split_lines(content: str) -> tuple[list[str], str, bool]:
    """Split *content* into lines plus the newline style to restore."""
    newline = "\r\n" if "\r\n" in content else "\n"
    return content.splitlines(), newline, content.endswith(("\n", "\r"))


def find_fence_defects(content: str) -> list[Defect]:
    """Return every fence defect in *content*, in file order."""
    lines, _, _ = _split_lines(content)
    defects: list[Defect] = []
    open_fence: _OpenFence | None = None

    for number, line in enumerate(lines, start=1):
        if open_fence is None:
            open_fence = _open_fence(line)
            continue

        match = _closes(line, open_fence)
        if match is None:
            continue
        if not match.group("info").strip():
            open_fence = None
            continue

        defects.append(Defect(line=number, kind=MALFORMED_CLOSING, text=line.rstrip()))
        # The malformed line opens the next block, mirroring the repair.
        open_fence = _open_fence(line) or open_fence

    if open_fence is not None:
        defects.append(
            Defect(line=len(lines), kind=UNCLOSED_BLOCK, text=open_fence.closing.strip()),
        )
    return defects


def repair_markdown_fences(content: str) -> str:
    """Return *content* with every fence defect repaired.

    Idempotent: repairing already-repaired content returns it unchanged.
    """
    lines, newline, trailing_newline = _split_lines(content)
    result: list[str] = []
    open_fence: _OpenFence | None = None

    for line in lines:
        if open_fence is None:
            result.append(line)
            open_fence = _open_fence(line)
            continue

        match = _closes(line, open_fence)
        if match is None:
            result.append(line)
            continue
        if not match.group("info").strip():
            result.append(line)
            open_fence = None
            continue

        result.append(open_fence.closing)
        result.append(line)
        open_fence = _open_fence(line) or open_fence

    if open_fence is not None:
        result.append(open_fence.closing)

    return newline.join(result) + (newline if trailing_newline else "")


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
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Error: cannot read {file_path}: {exc}", file=sys.stderr)
            return 2

        defects = find_fence_defects(content)
        if not defects:
            continue
        results[str(file_path)] = defects

        if not args.write:
            continue
        try:
            file_path.write_text(repair_markdown_fences(content), encoding="utf-8")
        except OSError as exc:
            print(f"Error: cannot write {file_path}: {exc}", file=sys.stderr)
            return 2
        wrote.append(str(file_path))

    _report(results, as_json=args.json, wrote=wrote)
    return 1 if (results and not args.write) else 0


if __name__ == "__main__":
    sys.exit(main())
