#!/usr/bin/env python3
"""Distill one large text artifact into a short markdown digest, once.

Deterministic, no model calls. The digest is keyed by the first 16 hex
characters of the content sha256 plus the option values, so a repeat call with
the same content and options reuses the stored digest instead of rewriting it.

Kinds:
    diff: per-file added/removed/hunk table, then hunk headers with line numbers.
    text: deduplicated signal lines (errors, failures), then head and tail lines.

Exit Codes:
    0: Success
    1: Error - Logic error
    2: Error - Invalid arguments or missing file
    3: Error - Unreadable input or output write failure

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _resolve_paths_lib_dir() -> Path:
    """Return the lib directory that contains the portability helper."""
    # ADR-047 keeps this bootstrap inline because imports need sys.path first.
    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        lib_dir = Path(plugin_root) / "lib"
    else:
        lib_dir = Path(__file__).resolve().parents[3] / "lib"

    if not os.path.isdir(lib_dir):
        raise RuntimeError(
            "Expected portability helper lib directory not found: "
            f"{lib_dir}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
            "plugin root, or run from an ai-agents checkout."
        )
    return lib_dir.resolve()


_LIB_DIR = _resolve_paths_lib_dir()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from paths import artifact_dir  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_EXTERNAL = 3

LINE_CAP = 240
DEFAULT_MAX_MATCHES = 40
DEFAULT_EDGE_LINES = 15
DISTILL_SUBDIR = Path("scratch") / "distill"
STDIN_LABEL = "stdin"

SIGNAL_RE = re.compile(
    r"\b(error|fail(ed|ure)?|exception|traceback|fatal|panic|warn(ing)?)\b",
    re.IGNORECASE,
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
DIGITS_RE = re.compile(r"\d+")
# Every control character except tab, plus the Unicode line and paragraph
# separators. ESC starts an ANSI sequence, a lone CR rewrites a terminal line,
# and a newline in a source name would start a new digest line.
CONTROL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029]")


@dataclass
class FileStat:
    """Per-file counts parsed from a unified diff."""

    path: str
    added: int = 0
    removed: int = 0
    hunks: int = 0


@dataclass
class DiffScan:
    """Result of scanning a unified diff."""

    files: list[FileStat] = field(default_factory=list)
    hunk_headers: list[tuple[int, str]] = field(default_factory=list)


def _visible(match: re.Match[str]) -> str:
    code = ord(match.group())
    return f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}"


def neutralize(text: str) -> str:
    """Replace each control character with a visible escape such as ``\\x1b``.

    The digest quotes artifact lines and source names that an attacker can
    choose. A raw ESC, CR, or newline would reach whatever prints or parses the
    digest. A line that already holds a literal ``\\x1b`` reads the same after
    this step, which costs a little fidelity and keeps the digest inert.
    """
    return CONTROL_RE.sub(_visible, text)


def clip(line: str) -> str:
    """Neutralize control characters, then truncate a quoted line to LINE_CAP characters."""
    safe = neutralize(line)
    return safe if len(safe) <= LINE_CAP else safe[:LINE_CAP]


def cell(text: str) -> str:
    """Return ``text`` clipped and safe inside one markdown table cell.

    A ``|`` would end the cell and add a column, so it is escaped. A backslash
    in the text would consume that escape (``\\|`` reads as a literal backslash
    and a bare pipe), so each backslash is doubled before the control-character
    escapes are added; those keep their single backslash. A cut at ``LINE_CAP``
    can leave an odd run of trailing backslashes, which would escape whatever
    follows the cell, so the last one is dropped.
    """
    safe = clip(text.replace("\\", "\\\\"))
    if (len(safe) - len(safe.rstrip("\\"))) % 2:
        safe = safe[:-1]
    return safe.replace("|", "\\|")


def detect_kind(lines: list[str]) -> str:
    """Return "diff" or "text" for the given lines."""
    has_old = False
    has_new = False
    for line in lines:
        if line.startswith("diff --git "):
            return "diff"
        has_old = has_old or line.startswith("--- ")
        has_new = has_new or line.startswith("+++ ")
    return "diff" if has_old and has_new else "text"


def _path_from_git_header(line: str) -> str:
    rest = line[len("diff --git ") :]
    marker = rest.rfind(" b/")
    return rest[marker + 3 :] if marker >= 0 else rest


def _path_from_plus_header(line: str) -> str:
    path = line[4:].split("\t", 1)[0]
    return path[2:] if path.startswith("b/") else path


def _hunk_lengths(match: re.Match[str]) -> tuple[int, int]:
    old_len, new_len = match.group(1), match.group(2)
    return (1 if old_len is None else int(old_len), 1 if new_len is None else int(new_len))


def _consume_body(line: str, current: FileStat, old_left: int, new_left: int) -> tuple[int, int]:
    """Apply one hunk body line to the counts; return the remaining line budgets."""
    if line.startswith("+"):
        current.added += 1
        return old_left, new_left - 1
    if line.startswith("-"):
        current.removed += 1
        return old_left - 1, new_left
    if line.startswith("\\"):
        return old_left, new_left
    return old_left - 1, new_left - 1


def scan_diff(lines: list[str]) -> DiffScan:
    """Count added, removed, and hunk totals per file and collect hunk headers."""
    scan = DiffScan()
    current: FileStat | None = None
    plus_seen = False
    old_left = new_left = 0
    for number, line in enumerate(lines, start=1):
        if old_left > 0 or new_left > 0:
            assert current is not None
            old_left, new_left = _consume_body(line, current, old_left, new_left)
            continue
        hunk = HUNK_RE.match(line)
        if line.startswith("diff --git "):
            current = FileStat(_path_from_git_header(line))
            scan.files.append(current)
            plus_seen = False
        elif line.startswith("+++ "):
            if current is None or plus_seen:
                current = FileStat(_path_from_plus_header(line))
                scan.files.append(current)
            plus_seen = True
        elif hunk and current is not None:
            current.hunks += 1
            scan.hunk_headers.append((number, line))
            old_left, new_left = _hunk_lengths(hunk)
    return scan


def render_diff(lines: list[str], max_matches: int) -> list[str]:
    """Render the diff-kind digest body."""
    scan = scan_diff(lines)
    out = ["", "## Files", "", "| path | added | removed | hunks |", "|---|---|---|---|"]
    for stat in scan.files:
        out.append(f"| {cell(stat.path)} | {stat.added} | {stat.removed} | {stat.hunks} |")
    out += ["", "## Hunk headers", ""]
    for number, header in scan.hunk_headers[:max_matches]:
        out.append(f"- L{number}: {clip(header)}")
    omitted = len(scan.hunk_headers) - max_matches
    if omitted > 0:
        out.append(f"- {omitted} more omitted")
    return out


def collect_signals(lines: list[str]) -> dict[str, list[int]]:
    """Group signal lines by digit-collapsed text; value is [first line, count]."""
    groups: dict[str, list[int]] = {}
    for number, line in enumerate(lines, start=1):
        if not SIGNAL_RE.search(line):
            continue
        # Collapse digits on the raw line first: clip() writes control characters
        # as \x1b-style escapes, and collapsing after that would erase their digits.
        key = clip(DIGITS_RE.sub("#", line))
        if key in groups:
            groups[key][1] += 1
        else:
            groups[key] = [number, 1]
    return groups


def render_signals(lines: list[str], max_matches: int) -> list[str]:
    """Render the signal-lines section."""
    out = ["", "## Signal lines", ""]
    groups = collect_signals(lines)
    if not groups:
        return [*out, "- none"]
    for key, (first, count) in list(groups.items())[:max_matches]:
        out.append(f"- L{first} (x{count}): {key}")
    omitted = len(groups) - max_matches
    if omitted > 0:
        out.append(f"- {omitted} more omitted")
    return out


def _numbered(lines: list[str], start: int) -> list[str]:
    return [f"{start + i}: {clip(line)}" for i, line in enumerate(lines)]


def render_edges(lines: list[str], edge_lines: int) -> list[str]:
    """Render the whole text, or its head and tail with 1-based line numbers."""
    if len(lines) <= 2 * edge_lines:
        return ["", "## Full text", "", *_numbered(lines, 1)]
    tail_start = len(lines) - edge_lines
    return [
        "",
        f"## First {edge_lines} lines",
        "",
        *_numbered(lines[:edge_lines], 1),
        "",
        f"## Last {edge_lines} lines",
        "",
        *_numbered(lines[tail_start:], tail_start + 1),
    ]


def render_text(lines: list[str], max_matches: int, edge_lines: int) -> list[str]:
    """Render the text-kind digest body."""
    return [*render_signals(lines, max_matches), *render_edges(lines, edge_lines)]


def build_digest(data: bytes, source: str, max_matches: int, edge_lines: int) -> tuple[str, str]:
    """Return (kind, digest markdown) for the raw bytes."""
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    kind = detect_kind(lines)
    header = [
        f"# Digest: {clip(source)}",
        "",
        f"- source: {clip(source)}",
        f"- sha256: {hashlib.sha256(data).hexdigest()}",
        f"- kind: {kind}",
        f"- raw bytes: {len(data)}",
        f"- raw lines: {len(lines)}",
    ]
    body = (
        render_diff(lines, max_matches)
        if kind == "diff"
        else render_text(lines, max_matches, edge_lines)
    )
    return kind, "\n".join([*header, *body]) + "\n"


def cache_key(data: bytes, source: str, max_matches: int, edge_lines: int) -> str:
    """Content hash prefix, source hash, and option values.

    The digest header names its source, so two sources with the same bytes
    need separate cache files or each call would overwrite the other.
    """
    prefix = hashlib.sha256(data).hexdigest()[:16]
    origin = hashlib.sha256(source.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{origin}-m{max_matches}-e{edge_lines}"


def find_repo_root(start: Path) -> Path | None:
    """Walk up from start to the first directory holding a .git entry."""
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def default_out_dir(cwd: Path) -> Path:
    """Digest directory via the portability helper; honors AI_AGENTS_ARTIFACT_ROOT."""
    root = find_repo_root(cwd.resolve())
    return Path(artifact_dir(DISTILL_SUBDIR, base=root))


def read_input(path: str) -> tuple[bytes, str]:
    """Read bytes from PATH or stdin ("-"). Raises FileNotFoundError, OSError."""
    if path == "-":
        return sys.stdin.buffer.read(), STDIN_LABEL
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(path)
    return target.read_bytes(), path


@dataclass
class Result:
    """Outcome of one distill call."""

    digest: Path
    cached: bool
    kind: str
    raw_bytes: int
    digest_bytes: int

    def as_json(self) -> str:
        ratio = round(self.digest_bytes / self.raw_bytes, 3) if self.raw_bytes else 0.0
        return json.dumps(
            {
                "digest": str(self.digest),
                "cached": self.cached,
                "kind": self.kind,
                "raw_bytes": self.raw_bytes,
                "digest_bytes": self.digest_bytes,
                "ratio": ratio,
            }
        )


def is_trusted_cache(target: Path, encoded: bytes) -> bool:
    """A cached digest counts only as a regular file whose bytes match a fresh build.

    A planted or stale file at the key path is not trusted, and a symlink is
    never followed.
    """
    if target.is_symlink() or not target.is_file():
        return False
    return target.read_bytes() == encoded


def atomic_write(target: Path, encoded: bytes) -> None:
    """Write through a temp file and os.replace, which replaces a symlink, not its target."""
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".distill-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
        os.replace(tmp, target)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


def distill(data: bytes, source: str, out_dir: Path, max_matches: int, edge_lines: int) -> Result:
    """Write the digest unless an identical one exists. Raises OSError on write failure."""
    target = out_dir / f"{cache_key(data, source, max_matches, edge_lines)}.md"
    kind, digest = build_digest(data, source, max_matches, edge_lines)
    encoded = digest.encode("utf-8")
    if is_trusted_cache(target, encoded):
        return Result(target, True, kind, len(data), len(encoded))
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(target, encoded)
    return Result(target, False, kind, len(data), len(encoded))


def non_negative(value: str) -> int:
    """argparse type: integer >= 0."""
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help='Input file, or "-" for stdin')
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--max-matches", type=non_negative, default=DEFAULT_MAX_MATCHES)
    parser.add_argument("--edge-lines", type=non_negative, default=DEFAULT_EDGE_LINES)
    parser.add_argument("--format", choices=("path", "json"), default="path")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        data, source = read_input(args.path)
    except FileNotFoundError:
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as error:
        print(f"error: cannot read {args.path}: {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    out_dir = args.out_dir or default_out_dir(Path.cwd())
    try:
        result = distill(data, source, out_dir, args.max_matches, args.edge_lines)
    except OSError as error:
        print(f"error: cannot write digest: {error}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(result.as_json() if args.format == "json" else result.digest)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
