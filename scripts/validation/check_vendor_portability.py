#!/usr/bin/env python3
"""Fail CI when a vendor-shipped script hard-codes an upstream-only path.

Issue #2050: skills in a vendored plugin install hard-code paths
(`.agents/`, `.claude/lib/`) that exist only in the upstream
`rjmurillo/ai-agents` checkout. In a consumer repo those paths do not
exist, so the skill fails or degrades silently. The fix (Phase 1) ships a
`.claude/lib/paths.py` helper with `resolve_artifact_root` (write path) and
`resolve_skill_resource` (read path). This check stops NEW scripts from
hard-coding those paths instead of routing through the helper.

What it flags:
  A Python file under a scanned skill-scripts root that contains a non-docstring
  string literal or f-string text with `.agents`, `.agents/`, `.agents\\`,
  `.claude/lib`, or `.claude\\lib` AND does not import and use the
  portability helper (`paths`, exposing `resolve_artifact_root` /
  `resolve_skill_resource`). A file that imports the helper is assumed to
  resolve paths through it; the literal is then the documented lazy default
  or prose, not a hard-coded dependency. Comments and docstrings are ignored.

What it does NOT flag (Issue #2510, false-positive guards):
  * Raw-string regex patterns. A literal like ``r"\\.agents/"`` carries the
    raw-string prefix (``r``/``R``/``rb``/``Rb``...) and a backslash-escaped
    dot (``\\.``); together those signals are overwhelmingly a regex pattern
    that *matches* paths, not a path the script reads or writes. The literal
    has no I/O semantics and cannot be migrated through ``paths.py``.
  * CLI prose. A literal that lives inside a keyword argument named
    ``help``, ``description``, ``epilog``, ``metavar``, or ``usage`` (the
    argparse / Click / Typer conventions) is rendered to stderr by the CLI
    parser and never opened as a file. The skip is scoped to the line range
    of the keyword's value expression, so a real path elsewhere in the same
    file is still flagged.

Baseline ratchet:
  131 files across 30+ skills already hard-code these paths (Issue #2050).
  Phase 1 does not migrate them. To gate regressions without forcing that
  migration now, the current offenders are recorded in a baseline file
  (see `baseline_path()`). Files in the baseline are reported as known debt but
  do not fail the check. A NEW offender not in the baseline fails. Run with
  `--update-baseline` to regenerate the baseline after an intentional change
  (for example, after migrating a file off the baseline).

EXIT CODES (ADR-035):
  0 - Success: no new offenders (baseline-listed debt is allowed); OR
      no scan roots present (vendor install without `.claude/skills` is
      benign here, prints `[SKIP] no scan roots present`); OR
      `--update-baseline` wrote the baseline.
  1 - One or more NEW offenders found (not in the baseline).
  2 - Configuration error (repo root or baseline path invalid).
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

# Upstream-only path prefixes that break in a vendored consumer repo.
# `.claude/skills/` is intentionally NOT flagged: the `/review` pattern
# resolves skill resources via the helper's `.claude/skills/...` candidate,
# so a reference to it inside the helper or via the helper is correct.
_BANNED_PATH = re.compile(r"\.agents(?:[\\/]+|['\"]|$)|\.claude[\\/]+lib(?:[\\/]+|['\"]|$)")
_STRING_TOKEN_TYPES = {tokenize.STRING}
if hasattr(tokenize, "FSTRING_MIDDLE"):
    _STRING_TOKEN_TYPES.add(tokenize.FSTRING_MIDDLE)

# Helper function names exposed by .claude/lib/paths.py.
_HELPER_FUNCTIONS: frozenset[str] = frozenset(
    {"resolve_artifact_root", "resolve_skill_resource"}
)

# Keyword argument names whose value is CLI prose, not an I/O path.
# When `.agents/` or `.claude/lib/` appears inside one of these kwargs
# (argparse `help=`, `description=`, `epilog=`, `metavar=`, `usage=`; Click
# and Typer follow the same convention), the literal is rendered onto
# stderr by the CLI parser. It never opens or writes a file, so it cannot
# be migrated through the portability helper and must not be flagged.
# Issue #2510.
_PROSE_KWARGS: frozenset[str] = frozenset(
    {"help", "description", "epilog", "metavar", "usage"}
)

# Directories scanned for vendor-shipped scripts.
_SCAN_ROOTS: tuple[str, ...] = (".claude/skills",)

# Baseline of known pre-existing offenders, relative to repo root, one
# POSIX path per line. Comments (`#`) and blank lines are ignored.
BASELINE_FILENAME = "vendor_portability_baseline.txt"


@dataclass
class Offender:
    """A scanned file that hard-codes a banned path without the helper."""

    relpath: str
    line: int
    excerpt: str


def baseline_path(repo_root: Path) -> Path:
    """Return the baseline file path co-located with this script."""
    return repo_root / "scripts" / "validation" / BASELINE_FILENAME


def load_baseline(path: Path) -> set[str]:
    """Load the baseline allowlist of known offenders (POSIX relpaths)."""
    if not path.is_file():
        return set()
    entries: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return entries


def scan_roots(repo_root: Path) -> list[Path]:
    """Return the scan-root directories that exist under repo_root."""
    return [repo_root / r for r in _SCAN_ROOTS if (repo_root / r).is_dir()]


def _routes_through_helper(content: str) -> bool:
    """True when the file imports and uses the portability helper."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    paths_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "paths":
                    paths_aliases.add(alias.asname or "paths")
        if isinstance(node, ast.ImportFrom) and node.module == "paths":
            if any(alias.name in _HELPER_FUNCTIONS for alias in node.names):
                return True

    if not paths_aliases:
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr not in _HELPER_FUNCTIONS:
            continue
        if isinstance(node.value, ast.Name) and node.value.id in paths_aliases:
            return True
    return False


def _docstring_lines(content: str) -> set[int]:
    """Return line numbers occupied by module, class, and function docstrings."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()

    lines: set[int] = set()
    nodes: list[ast.AST] = [tree]
    nodes.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    )
    for node in nodes:
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            continue
        start = first.lineno
        end = getattr(first, "end_lineno", start)
        lines.update(range(start, end + 1))
    return lines


def _prose_lines(content: str) -> set[int]:
    """Return line numbers occupied by CLI prose keyword-arg values.

    Walks the AST for every ``ast.Call`` and records the line range of any
    keyword whose name is in ``_PROSE_KWARGS`` (``help``, ``description``,
    ``epilog``, ``metavar``, ``usage``). The value may be a single string,
    a tuple/list of strings, a parenthesized concatenation (implicit string
    joining), or a ``+``/``%`` expression mixing strings; the line span of
    the entire value expression is marked so any banned-path token sitting
    inside that span is treated as prose, not as a path operation.

    Issue #2510. Cases like ``argparse.ArgumentParser(epilog=...)`` and
    ``parser.add_argument("--out", help="...")`` are the primary motivators;
    Click ``@click.option(..., help=...)`` and Typer follow the same
    convention and are exempted by the same rule.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()

    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg is None or kw.arg not in _PROSE_KWARGS:
                continue
            start = getattr(kw.value, "lineno", None)
            end = getattr(kw.value, "end_lineno", start)
            if start is None:
                continue
            lines.update(range(start, (end or start) + 1))
    return lines


# Recognised string-literal prefixes that mark a raw string.
# A raw string disables Python's own backslash interpretation, so any
# ``\.`` inside one is the regex escape for a literal dot. Combined with a
# banned path it is overwhelmingly a regex pattern matching paths, not a
# real path the script writes. Issue #2510. The ``f`` letters cover raw
# f-string prefixes (``rf``/``fr``/``Rf``...), which tokenize as a single
# STRING token on Python < 3.12.
_RAW_STRING_PREFIX = re.compile(r"^[bBuUfF]*[rR][bBuUfF]*")


def _is_raw_string_regex(
    token_text: str,
    is_fstring_middle: bool = False,
    is_raw_fstring: bool = False,
) -> bool:
    """True when ``token_text`` is raw-string text containing ``\\.``.

    For a ``tokenize.STRING`` token, ``token_text`` is the raw source slice
    (prefix + quotes + body) and the raw-ness is read from the prefix. For a
    ``FSTRING_MIDDLE`` token (Python 3.12+ splits f-strings into
    FSTRING_START/MIDDLE/END), the text carries no prefix, so the caller
    passes ``is_raw_fstring`` derived from the enclosing FSTRING_START token.

    We require both the raw-string signal and a literal backslash-escaped
    dot in the body. Real path strings never escape the dot; matching
    ``r".agents/x"`` (no backslash) is rare and intentionally still flagged
    so a missing-escape regex does not become a silent bypass.
    """
    if is_fstring_middle:
        if not is_raw_fstring:
            return False
    elif not _RAW_STRING_PREFIX.match(token_text):
        return False
    return "\\." in token_text


def _first_banned_line(content: str) -> tuple[int, str] | None:
    """Return the first banned path in a non-docstring string literal."""
    skip_lines = _docstring_lines(content) | _prose_lines(content)
    reader = io.StringIO(content).readline
    fstring_start = getattr(tokenize, "FSTRING_START", None)
    fstring_middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    fstring_end = getattr(tokenize, "FSTRING_END", None)
    is_raw_fstring = False
    try:
        tokens = tokenize.generate_tokens(reader)
        for token in tokens:
            if token.type == fstring_start:
                is_raw_fstring = "r" in token.string.lower()
                continue
            if token.type == fstring_end:
                is_raw_fstring = False
                continue
            if token.type not in _STRING_TOKEN_TYPES or token.start[0] in skip_lines:
                continue
            if not _BANNED_PATH.search(token.string):
                continue
            if _is_raw_string_regex(
                token.string,
                is_fstring_middle=token.type == fstring_middle,
                is_raw_fstring=is_raw_fstring,
            ):
                continue
            return token.start[0], token.line.strip()
    except tokenize.TokenError:
        return None
    return None


def collect_offenders(repo_root: Path) -> list[Offender]:
    """Find files that hard-code a banned path without the helper.

    A file is an offender when it contains a banned path AND does not route
    through the portability helper. The portability helper itself
    (`.claude/lib/paths.py`) lives outside the scan roots, so it is never
    scanned.
    """
    offenders: list[Offender] = []
    for root in scan_roots(repo_root):
        for py_file in sorted(root.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _routes_through_helper(content):
                continue
            hit = _first_banned_line(content)
            if hit is None:
                continue
            line_no, excerpt = hit
            relpath = py_file.relative_to(repo_root).as_posix()
            offenders.append(Offender(relpath, line_no, excerpt))
    return offenders


def split_offenders(
    offenders: list[Offender],
    baseline: set[str],
) -> tuple[list[Offender], list[Offender]]:
    """Partition offenders into (new, known) by baseline membership."""
    new: list[Offender] = []
    known: list[Offender] = []
    for off in offenders:
        (known if off.relpath in baseline else new).append(off)
    return new, known


def format_report(new: list[Offender], known: list[Offender]) -> str:
    """Format a human-readable report."""
    lines: list[str] = []
    if not new:
        lines.append("[PASS] No new vendor-portability offenders.")
        if known:
            lines.append(
                f"       {len(known)} known offender(s) tracked in the baseline "
                "(Issue #2050 migration debt)."
            )
        return "\n".join(lines) + "\n"

    lines.append(f"[FAIL] {len(new)} new vendor-portability offender(s) found.")
    lines.append("")
    lines.append(
        "These files hard-code an upstream-only path (.agents/ or "
        ".claude/lib/) and do not route through the portability helper."
    )
    lines.append(
        "Use .claude/lib/paths.py: resolve_artifact_root() for write paths, "
        "resolve_skill_resource() for read paths. See Issue #2050."
    )
    lines.append("")
    for off in new:
        lines.append(f"  - {off.relpath}:{off.line}")
        lines.append(f"      {off.excerpt!r}")
    lines.append("")
    lines.append(
        "If this offender is intentional and cannot be made portable, add it "
        "to scripts/validation/vendor_portability_baseline.txt with a comment "
        "or run --update-baseline."
    )
    return "\n".join(lines) + "\n"


def write_baseline(path: Path, offenders: list[Offender]) -> None:
    """Write the baseline file from the current offender set."""
    header = [
        "# Vendor-portability baseline (Issue #2050).",
        "# Pre-existing scripts that hard-code .agents/ or .claude/lib/ paths.",
        "# check_vendor_portability.py allows these but fails on NEW offenders.",
        "# Regenerate: python3 scripts/validation/check_vendor_portability.py --update-baseline",
        "",
    ]
    body = sorted({off.relpath for off in offenders})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Fail CI on new hard-coded upstream-only paths in skills.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to the script's grandparent).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Regenerate the baseline from the current offenders, then exit 0.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)

    repo_root = args.repo_root
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    if not repo_root.is_dir():
        print(f"[FAIL] repo root not found: {repo_root}", file=sys.stderr)
        return 2

    roots = scan_roots(repo_root)
    if not roots:
        print("[SKIP] no scan roots present (.claude/skills).")
        return 0

    offenders = collect_offenders(repo_root)

    bpath = baseline_path(repo_root)
    if args.update_baseline:
        try:
            write_baseline(bpath, offenders)
        except OSError as exc:
            print(f"[FAIL] cannot write baseline {bpath}: {exc}", file=sys.stderr)
            return 2
        print(f"[OK] wrote baseline: {bpath} ({len(offenders)} entr(ies))")
        return 0

    baseline = load_baseline(bpath)
    new, known = split_offenders(offenders, baseline)
    print(format_report(new, known))
    return 1 if new else 0


if __name__ == "__main__":
    raise SystemExit(main())
