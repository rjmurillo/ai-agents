#!/usr/bin/env python3
"""Heuristic check that mirror-claims carry a canonical path or structural evidence.

This script enforces the spirit of `.claude/rules/canonical-source-mirror.md`
at the file-rule layer. When a Python source file under
`.claude/hooks/`, `scripts/validation/`, `build/scripts/`, or `.claude/skills/` contains a
docstring or top-level comment that asserts the file "matches", "mirrors",
or is "aligned with" some other source, this check verifies that the file
carries a canonical path or structural evidence. A path is a path-like
reference (e.g. `scripts/foo.py`, `.project-toolkit/architecture/ADR-001.md`,
`build/scripts/bar.py`) in the docstrings or top-level comments. Structural
evidence is listed below.

Evidence ranks per `scripts/validation/mirror_evidence.py`: a path reference,
a conformance test identifier, a shared import of a project name, or a
"generated from" statement each satisfies the claim. A claim that carries a
hand-copied contract with none of the structural forms also gets an advisory
copied-contract finding that recommends eliminating the copy.

The check is intentionally a heuristic. It is designed to catch the
specific failure mode documented in the PR #1887 retrospective
(`.project-toolkit/retrospective/2026-05-05-pr-1887-iteration-paradox.md`): a
docstring that says "matches X" with no path, no quoted contract, and no
divergence section. False positives are acceptable; the false-negative
case (the bare "matches X" with no citation) is the bug this rule is
fighting.

Failure mode by default: WARNING (exit 0 with non-empty stderr-style
output on stdout). Set the environment variable `STRICT_CANONICAL_CHECK=1`
to upgrade warnings to a hard FAIL (exit 1).

Growth is blocked separately: `scripts/ci/canonical_citations_count_ratchet.py`
freezes the number of violations `STRICT_CANONICAL_CHECK=1` reports at the
value in `scripts/ci/canonical_citations_count_baseline.txt`, so the count can
fall and cannot rise (issue #5636).

EXIT CODES:
  0 - Success (no violations; OR violations only in soft-warn mode; OR no
      scan roots present, which prints `[SKIP] no scan roots present` and
      treats the absence as benign: vendor installs without `.claude/`
      should not be a hard failure here)
  1 - Violations found AND STRICT_CANONICAL_CHECK=1
  2 - Configuration error (currently unused; reserved for future paths
      that genuinely cannot proceed)
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

# The typed contract, package path (evidence.py states why). This file runs as
# a script, so the repository root is not on sys.path until it is inserted.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import (  # noqa: E402
    REASON_ADVISORY_FINDINGS,
    REASON_TREE_ABSENT,
    REASON_VIOLATIONS_FOUND,
    WORKING_TREE,
    CheckOutcome,
)
from scripts.validation.mirror_evidence import (  # noqa: E402
    REMEDIATION,
    copied_contract_marker,
    imported_project_names,
    structural_evidence,
)

_VALIDATOR = "validate_canonical_citations"
_SCOPE = "docstrings and top-level comments that claim to mirror a source"

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
    r"|\.project-toolkit/[\w./-]+"
    r"|\.github/[\w./-]+"
    r"|scripts/[\w./-]+"
    r"|build/[\w./-]+"
    r"|src/[\w./-]+"
    r"|tests/[\w./-]+"
    r"|templates/[\w./-]+"
    r"|[\w./-]+\.(?:py|ps1|md|json|yaml|yml|sh)\b"
    r")"
)

# Fallback module-docstring extractor for source that does not parse as Python
# (ast.parse raised SyntaxError). Grabs the first leading triple-quoted string,
# skipping an optional shebang and any blank/comment lines before it. Handles
# both triple-double and triple-single quotes and the r/b/u/f string prefixes.
_MODULE_DOCSTRING_RE: re.Pattern[str] = re.compile(
    r"\A(?:\#![^\n]*\n)?(?:[ \t]*(?:\#[^\n]*)?\n)*"
    r"[ \t]*[rRbBuUfF]{0,2}(?P<quote>\"\"\"|''')(?P<body>.*?)(?P=quote)",
    re.DOTALL,
)


@dataclass
class Violation:
    """A file that triggers a mirror-claim with no canonical path or structural evidence."""

    path: Path
    matched_token: str
    excerpt: str


@dataclass
class CopyFinding:
    """A mirror-claim backed only by a hand-copied contract."""

    path: Path
    marker: str
    remediation: str = REMEDIATION


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
        # File does not parse (partial edit, mixed content). Fall back to a
        # regex grab of the leading triple-quoted module docstring so a
        # mirror-claim living only in that docstring is still scanned instead of
        # silently dropped. Top-of-file comments above are already collected
        # without parsing, so they are unaffected.
        match = _MODULE_DOCSTRING_RE.search(source)
        if match:
            docstring = match.group("body")
        else:
            print(
                "[SKIP] unparseable, module docstring not scanned",
                file=sys.stderr,
            )

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


def scan_file(path: Path, repo_root: Path = _PROJECT_ROOT) -> Violation | None:
    """Scan a single file for an uncited mirror-claim.

    Returns a Violation if the file's top-level docstring or comments
    contain a mirror-token but no path reference; otherwise None. Import
    ownership is judged against `repo_root`, the repository being scanned.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Violation(
            path=path,
            matched_token="read_error",
            excerpt=f"Unable to read file: {exc}",
        )

    text = _extract_docstring_and_top_comments(source)
    if not text:
        return None

    token = _find_mirror_token(text)
    if token is None:
        return None

    if _has_path_reference(text) or structural_evidence(
        text, imported_project_names(source, repo_root, path.parent)
    ):
        return None

    excerpt = _excerpt_for_token(text, token)
    return Violation(path=path, matched_token=token, excerpt=excerpt)


def scan_copied_contract(path: Path, repo_root: Path = _PROJECT_ROOT) -> CopyFinding | None:
    """Return a finding when a mirror-claim carries a copy no structure backs.

    Advisory only: it never changes the exit code and is not counted by the
    ratchet. Structural evidence (conformance test, shared import, generated
    marker) clears it, because the copy is then a checked projection.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    text = _extract_docstring_and_top_comments(source)
    if not text or _find_mirror_token(text) is None:
        return None
    marker = copied_contract_marker(text)
    if marker is None or structural_evidence(
        text, imported_project_names(source, repo_root, path.parent)
    ):
        return None
    return CopyFinding(path=path, marker=marker)


def collect_copy_findings(repo_root: Path) -> list[CopyFinding]:
    """Scan all configured roots for unbacked copied contracts."""
    findings = (
        scan_copied_contract(p, repo_root) for p in _iter_python_files(_scan_roots(repo_root))
    )
    return [f for f in findings if f is not None]


def collect_all(repo_root: Path) -> tuple[list[Violation], list[CopyFinding]]:
    """Scan every configured file once and return violations and copy findings."""
    violations: list[Violation] = []
    findings: list[CopyFinding] = []
    for path in _iter_python_files(_scan_roots(repo_root)):
        violation = scan_file(path, repo_root)
        if violation is not None:
            violations.append(violation)
        finding = scan_copied_contract(path, repo_root)
        if finding is not None:
            findings.append(finding)
    return violations, findings


def format_copy_findings(findings: list[CopyFinding]) -> str:
    """Format the advisory copied-contract section, empty when there are none."""
    if not findings:
        return ""
    lines = [f"[WARN] {len(findings)} copied-contract finding(s), advisory.", ""]
    for f in findings:
        lines.append(f"  - {f.path} (marker: {f.marker!r})")
    lines += ["", f"  {REMEDIATION}", ""]
    return "\n".join(lines)


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
        v = scan_file(path, repo_root)
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
        "in a docstring or top-level comment but carry no canonical path "
        "or structural evidence (conformance test, shared import, "
        "generated-from statement).",
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


def _no_roots_outcome() -> CheckOutcome:
    """Type the benign absence of every scan root as ``SKIP`` with ``tree.absent``."""
    return CheckOutcome.skipped(
        _VALIDATOR,
        reason=REASON_TREE_ABSENT,
        scope=_SCOPE,
        detail="no scan root present; a vendor install without .claude/ is not an error",
    )


def _violations_outcome(count: int, *, strict: bool) -> CheckOutcome:
    """Type uncited mirror-claims: ``advisory.findings`` by default, blocking in strict mode.

    Both are ``FAIL``. Only the reason differs, so a grep for the reason counts
    the warnings that exit 0 separately from the ones that blocked.
    """
    return CheckOutcome.failed(
        _VALIDATOR,
        reason=REASON_VIOLATIONS_FOUND if strict else REASON_ADVISORY_FINDINGS,
        revision=WORKING_TREE,
        scope=_SCOPE,
        findings=count,
        detail="strict mode, exit 1" if strict else "soft warning, exit 0",
    )


def _report_non_pass(outcome: CheckOutcome) -> None:
    """Print the typed result on stderr, leaving stdout's status lines unchanged.

    ``checks_citations`` parses this script's stdout for its first status token,
    so the typed line goes to the other stream.
    """
    print(outcome.report_line(), file=sys.stderr)


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
        _report_non_pass(_no_roots_outcome())
        return 0

    violations, copy_findings = collect_all(repo_root)
    print(format_report(violations, strict=args.strict))
    print(format_copy_findings(copy_findings), end="")

    if violations:
        _report_non_pass(_violations_outcome(len(violations), strict=args.strict))
    if violations and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
