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
  string literal with `.agents/` or `.claude/lib/` AND does not import the
  portability helper (`paths`, exposing `resolve_artifact_root` /
  `resolve_skill_resource`). A file that imports the helper is assumed to
  resolve paths through it; the literal is then the documented lazy default
  or prose, not a hard-coded dependency. Comments and docstrings are ignored.

Baseline ratchet:
  131 files across 30+ skills already hard-code these paths (Issue #2050).
  Phase 1 does not migrate them. To gate regressions without forcing that
  migration now, the current offenders are recorded in a baseline file
  (see BASELINE_PATH). Files in the baseline are reported as known debt but
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
_BANNED_PATH = re.compile(r"\.agents/|\.claude/lib/")

# Indicators that a file routes paths through the portability helper.
# Any of these substrings exempts the file (it is presumed to use the
# helper's lazy-default / candidate resolution rather than a hard-coded dep).
_HELPER_TOKENS: tuple[str, ...] = (
    "import paths",
    "from paths import",
    "resolve_artifact_root",
    "resolve_skill_resource",
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
    """True when the file imports or calls the portability helper."""
    return any(token in content for token in _HELPER_TOKENS)


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


def _first_banned_line(content: str) -> tuple[int, str] | None:
    """Return the first banned path in a non-docstring string literal."""
    doc_lines = _docstring_lines(content)
    reader = io.StringIO(content).readline
    try:
        tokens = tokenize.generate_tokens(reader)
        for token in tokens:
            if token.type != tokenize.STRING or token.start[0] in doc_lines:
                continue
            if _BANNED_PATH.search(token.string):
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
