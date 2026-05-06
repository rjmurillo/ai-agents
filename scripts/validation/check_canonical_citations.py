#!/usr/bin/env python3
"""Heuristic check that mirror-claims cite a canonical path.

This script enforces the spirit of `.claude/rules/canonical-source-mirror.md`
at the file-rule layer. When a Python source file under
`.claude/hooks/`, `scripts/validation/`, `build/scripts/`, or `.claude/skills/` contains a
docstring or top-level comment that asserts the file "matches", "mirrors",
or is "aligned with" some other source, this check verifies that within the
same file there is at least one path-like reference (e.g.
`scripts/foo.py`, `.agents/architecture/ADR-001.md`,
`build/scripts/bar.py`) somewhere in the docstrings or top-level comments.

The check is intentionally a heuristic. It is designed to catch the
specific failure mode documented in the PR #1887 retrospective
(`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`): a
docstring that says "matches X" with no path, no quoted contract, and no
divergence section. False positives are acceptable; the false-negative
case (the bare "matches X" with no citation) is the bug this rule is
fighting.

Failure mode by default: WARNING (exit 0 with non-empty stderr-style
output on stdout). Set the environment variable `STRICT_CANONICAL_CHECK=1`
to upgrade warnings to a hard FAIL (exit 1).

EXIT CODES:
  0 - Success (no violations, OR violations only in soft-warn mode)
  1 - Violations found AND STRICT_CANONICAL_CHECK=1
  2 - Configuration error (no scan roots present)
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Tokens that indicate a mirror-claim. Case-insensitive substring match.
# These are the surface indicators the rule is built on. Keep this list
# narrow; broadening it raises the false-positive rate without raising
# the false-negative coverage.
_MIRROR_TOKENS: tuple[str, ...] = (
    "matches the",
    "mirrors the",
    "mirrors ",
    "aligned with",
    "aligns with",
    "same as the",
    "identical to the",
)

# Heuristic path-like reference: at least one slash separating segments,
# anchored to a known repo-root prefix or ending in a known file
# extension. This is intentionally permissive; the goal is to confirm
# *some* concrete path appears, not to validate it.
_PATH_REF: re.Pattern[str] = re.compile(
    r"(?:"
    r"\.claude/[\w./-]+"
    r"|\.agents/[\w./-]+"
    r"|\.github/[\w./-]+"
    r"|scripts/[\w./-]+"
    r"|build/[\w./-]+"
    r"|src/[\w./-]+"
    r"|tests/[\w./-]+"
    r"|templates/[\w./-]+"
    r"|[\w./-]+\.(?:py|ps1|md|json|yaml|yml|sh)\b"
    r")"
)


@dataclass
class Violation:
    """A file that triggers a mirror-claim with no path citation."""

    path: Path
    matched_token: str
    excerpt: str


def _scan_roots(repo_root: Path) -> list[Path]:
    """Return the directories this check inspects."""
    candidates = [
        repo_root / ".claude" / "hooks",
        repo_root / "scripts" / "validation",
        repo_root / "build" / "scripts",
        repo_root / ".claude" / "skills",
    ]
    return [c for c in candidates if c.is_dir()]


def _iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield all .py files under the given roots, sorted for stability."""
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _extract_docstring_and_top_comments(source: str) -> str:
    """Return the module docstring concatenated with top-of-file comments.

    Top-of-file comments are the contiguous run of lines starting with
    '#' before the first non-comment, non-blank line (excluding a
    leading shebang). The module docstring, if present, is appended.

    The return value is the text the heuristic searches; it deliberately
    excludes function-level and class-level bodies, which would generate
    too many false positives for an unrelated codebase comment.
    """
    lines = source.splitlines()
    top_comments: list[str] = []
    i = 0
    if lines and lines[0].startswith("#!"):
        i = 1
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("#"):
            top_comments.append(stripped)
            i += 1
            continue
        break

    docstring = ""
    try:
        module = ast.parse(source)
        module_doc = ast.get_docstring(module)
        if module_doc:
            docstring = module_doc
    except SyntaxError:
        pass

    return "\n".join(top_comments + [docstring])


def _find_mirror_token(text: str) -> str | None:
    """Return the first mirror-token found in text, or None."""
    lower = text.lower()
    for token in _MIRROR_TOKENS:
        if token in lower:
            return token
    return None


def _has_path_reference(text: str) -> bool:
    """Return True if the text contains a path-like reference."""
    return bool(_PATH_REF.search(text))


def scan_file(path: Path) -> Violation | None:
    """Scan a single file for an uncited mirror-claim.

    Returns a Violation if the file's top-level docstring or comments
    contain a mirror-token but no path reference; otherwise None.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    text = _extract_docstring_and_top_comments(source)
    if not text:
        return None

    token = _find_mirror_token(text)
    if token is None:
        return None

    if _has_path_reference(text):
        return None

    excerpt = _excerpt_for_token(text, token)
    return Violation(path=path, matched_token=token, excerpt=excerpt)


def _excerpt_for_token(text: str, token: str) -> str:
    """Return a short excerpt around the first occurrence of the token."""
    lower = text.lower()
    idx = lower.find(token)
    if idx < 0:
        return text[:120]
    start = max(0, idx - 40)
    end = min(len(text), idx + len(token) + 80)
    return text[start:end].replace("\n", " ")


def collect_violations(repo_root: Path) -> list[Violation]:
    """Scan all configured roots and return the list of violations."""
    roots = _scan_roots(repo_root)
    if not roots:
        return []
    violations: list[Violation] = []
    for path in _iter_python_files(roots):
        v = scan_file(path)
        if v is not None:
            violations.append(v)
    return violations


def format_report(violations: list[Violation], strict: bool) -> str:
    """Format a human-readable report of violations."""
    if not violations:
        return "[PASS] No uncited mirror-claims found.\n"

    label = "[FAIL]" if strict else "[WARN]"
    lines = [
        f"{label} {len(violations)} uncited mirror-claim(s) found.",
        "",
        "These files contain a mirror-claim (matches/mirrors/aligned with) "
        "in a docstring or top-level comment but cite no path-like "
        "reference within those areas.",
        "",
        "See `.claude/rules/canonical-source-mirror.md` for what to do.",
        "",
    ]
    for v in violations:
        lines.append(f"  - {v.path}")
        lines.append(f"      token: {v.matched_token!r}")
        lines.append(f"      near: {v.excerpt!r}")
    lines.append("")
    if not strict:
        lines.append(
            "Note: this is a soft warning. Set STRICT_CANONICAL_CHECK=1 to "
            "upgrade warnings to a hard failure."
        )
        lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Heuristic check for uncited canonical-source mirror-claims.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (defaults to script's grandparent).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=os.environ.get("STRICT_CANONICAL_CHECK", "").lower() in ("1", "true"),
        help="Treat violations as a hard failure (exit 1).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    args = parse_args(argv)

    repo_root = args.repo_root
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    if not repo_root.is_dir():
        print(f"[FAIL] repo root not found: {repo_root}", file=sys.stderr)
        return 2

    roots = _scan_roots(repo_root)
    if not roots:
        print(
            "[SKIP] no scan roots present "
            "(.claude/hooks, scripts/validation, build/scripts, .claude/skills).",
        )
        return 0

    violations = collect_violations(repo_root)
    print(format_report(violations, strict=args.strict))

    if violations and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
