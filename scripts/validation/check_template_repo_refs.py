#!/usr/bin/env python3
"""Gate: shipped skill and agent templates must not cite this repository's issues or PRs.

Templates under ``templates/skills/`` and ``templates/agents/`` are vendored into
other repositories. An issue or PR number there means nothing to a consumer, and it
can collide with an unrelated issue in the consumer's own tracker. Describe the
rule or the behavior instead. Use a placeholder such as ``#<number>`` in examples.

Flagged forms:
    - ``issue #123``, ``issues #1 and #2``, ``PR #123``, ``Child 1 #123``
    - ``Issue 123`` (no hash)
    - ``(#123)`` and a bare ``#123`` of two or more digits
    - ``github.com/<owner>/<repo>/issues/123`` and ``.../pull/123``

Nothing is exempt. An allowlist would teach CI to look away.

CLI::

    uv run python scripts/validation/check_template_repo_refs.py
    uv run python scripts/validation/check_template_repo_refs.py <repo-root>

Exit codes (ADR-035):
    0 - Success (no repository issue or PR reference)
    1 - Logic error (one or more references found)
    2 - Config error (invalid repository root, or a scanned tree is missing)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCANNED_TREES = (Path("templates/skills"), Path("templates/agents"))

_NUM = r"\d+"
REF_PATTERN = re.compile(
    r"\b(?:[Ii]ssues?|PRs?|[Pp]ull requests?|Child \d+)\s*(?:#"
    + _NUM
    + r"|\d{3,})"
    + r"|github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/"
    + _NUM
    + r"|(?<![\w&/#])#"
    + r"\d{2,}\b"
)


def find_repo_refs(repo_root: Path) -> list[tuple[Path, int, str]]:
    """Return ``(relative path, line number, matched text)`` for each reference.

    Raises ``FileNotFoundError`` when a scanned tree is absent. A silently empty
    scan passes and proves nothing.
    """
    findings: list[tuple[Path, int, str]] = []
    for tree in SCANNED_TREES:
        root = repo_root / tree
        if not root.is_dir():
            msg = f"template tree not found: {root}"
            raise FileNotFoundError(msg)
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in REF_PATTERN.finditer(line):
                    findings.append((path.relative_to(repo_root), lineno, match.group(0)))
    return findings


def _report(findings: list[tuple[Path, int, str]]) -> None:
    print(
        f"[FAIL] {len(findings)} repository issue or PR reference(s) in shipped templates. "
        "Vendored installs cannot resolve these numbers, and they can collide with "
        "the consumer's own issues:",
        file=sys.stderr,
    )
    for rel, lineno, text in findings:
        print(f"  {rel.as_posix()}:{lineno}  {text}", file=sys.stderr)
    print(
        "\nFix: state the rule or behavior without the number. Use `#<number>` in "
        "examples. Do not add an exemption.",
        file=sys.stderr,
    )


def validate_template_repo_refs(repo_root: Path) -> bool:
    """Return True when no scanned template cites a repository issue or PR.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        findings = find_repo_refs(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return False
    if findings:
        _report(findings)
    return not findings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        findings = find_repo_refs(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    if findings:
        _report(findings)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
