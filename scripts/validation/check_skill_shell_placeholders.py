#!/usr/bin/env python3
"""Gate: no bare ``$<digit>`` inside a shell fence of a skill ``SKILL.md``.

The skill loader substitutes positional arguments into the skill body before
the model reads it. A shell fence that holds an awk program such as
``substr($0, 10)`` is rewritten to ``substr(6676, 10)`` when the skill runs with
``args`` set to ``6676``. Issue #6743: the pr-autofix worktree lookup returned an
empty path because of it.

Only shell fences are scanned (info string ``bash``, ``sh``, ``shell``, ``zsh``,
``console``). Prose and non-shell fences, such as the ``$0`` and ``$25`` cells in
a Markdown cost table, are left alone, and so are the intentional ``$0`` and
``$1`` argument placeholders that ``validate-pr-description`` documents in a
prose table. An unlabeled fence is skipped because its language is unknown.

The fix for an awk program is ``$(0)``, ``$(1)``, ``$(2)``: valid awk, with no
digit directly after the dollar sign. The gate carries no allowlist.

CLI::

    uv run python scripts/validation/check_skill_shell_placeholders.py
    uv run python scripts/validation/check_skill_shell_placeholders.py <repo-root>

Exit codes (ADR-035):
    0 - Success (no bare placeholder in any shell fence)
    1 - Logic error (one or more findings)
    2 - Config error (invalid repository root, or no skills found)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKILL_TREE = Path(".claude/skills")
_SKILL_MANIFEST = "SKILL.md"

_SHELL_LANGS = frozenset({"bash", "sh", "shell", "zsh", "console", "shellscript"})
_FENCE_OPEN = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})\s*(?P<info>[^`]*)$")
_QUOTE_PREFIX = re.compile(r"^\s*(?:>\s?)+")
_PLACEHOLDER = re.compile(r"\$[0-9]")


def _fence_language(info: str) -> str:
    """Return the lowercase language word of a fence info string, or ''."""
    words = info.strip().split()
    return words[0].lower() if words else ""


def find_placeholders(text: str) -> list[tuple[int, str]]:
    """Return ``(line number, line)`` for each ``$<digit>`` in a shell fence.

    Fence tracking follows CommonMark: a fence closes on a bare line of the same
    character with at least as many characters as the opener, so a longer outer
    fence can hold a shorter inner one. A leading blockquote marker (``>``) is
    stripped first, because the loader substitutes the whole body.
    """
    findings: list[tuple[int, str]] = []
    open_char = ""
    open_len = 0
    in_shell = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = _QUOTE_PREFIX.sub("", raw)
        if open_char:
            stripped = line.strip()
            if stripped and set(stripped) == {open_char} and len(stripped) >= open_len:
                open_char = ""
                open_len = 0
                in_shell = False
            elif in_shell and _PLACEHOLDER.search(line):
                findings.append((number, line.strip()))
            continue
        match = _FENCE_OPEN.match(line)
        if match:
            fence = match.group("fence")
            open_char = fence[0]
            open_len = len(fence)
            in_shell = _fence_language(match.group("info")) in _SHELL_LANGS
    return findings


def find_skill_findings(repo_root: Path) -> list[tuple[Path, int, str]]:
    """Return ``(relative path, line, text)`` for every finding across the tree.

    Raises ``FileNotFoundError`` when the tree holds no SKILL.md. A silently
    empty scan passes and proves nothing, so absence is a configuration error.
    """
    tree = repo_root / SKILL_TREE
    manifests = sorted(tree.glob(f"*/{_SKILL_MANIFEST}")) if tree.is_dir() else []
    if not manifests:
        msg = f"no {_SKILL_MANIFEST} found under {tree}"
        raise FileNotFoundError(msg)

    findings: list[tuple[Path, int, str]] = []
    for manifest in manifests:
        text = manifest.read_text(encoding="utf-8")
        rel = manifest.relative_to(repo_root)
        findings.extend((rel, line, body) for line, body in find_placeholders(text))
    return findings


def _report(findings: list[tuple[Path, int, str]]) -> None:
    """Print the failure report for a non-empty findings list."""
    print(
        f"[FAIL] {len(findings)} bare $<digit> placeholder(s) inside skill shell "
        "fences. The skill loader replaces them with the invocation arguments, "
        "so the shell command that runs differs from the one on disk:",
        file=sys.stderr,
    )
    for rel, line, body in findings:
        print(f"  {rel.as_posix()}:{line}  {body}", file=sys.stderr)
    print(
        "\nFix: write awk fields as $(0), $(1), $(2), or restructure the command "
        "so no digit follows the dollar sign. Do not add an exemption. "
        "Refs issue #6743.",
        file=sys.stderr,
    )


def validate_skill_shell_placeholders(repo_root: Path) -> bool:
    """Return True when no skill shell fence holds a bare ``$<digit>``.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    try:
        findings = find_skill_findings(repo_root)
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
        findings = find_skill_findings(repo_root)
    except FileNotFoundError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    if findings:
        _report(findings)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
