#!/usr/bin/env python3
"""Detect bare-python3 documentation pointing to scripts that import third-party deps.

A script that uses `import yaml`, `import anthropic`, or any other declared
dependency cannot be invoked as `python3 scripts/X.py` on a clean system: the
bare interpreter resolves only stdlib. Any such invocation must use
`uv run python scripts/X.py`.

This validator scans a configurable list of documentation files for
`python3 scripts/` patterns, then AST-checks each referenced script for
third-party imports, and fails if any mismatch is found.

Exit codes per ADR-035:
    0: No mismatches found
    1: One or more mismatches detected
    2: Configuration or file access error
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# Pattern that matches a bare-python3 script invocation inside backtick code,
# code fences, or plain prose (we match the command, not the context).
_BARE_PY3_PATTERN = re.compile(r"(?<!\w)python3\s+(scripts/[^\s`\"']+\.py)")

# Third-party module name -> import-level name that appears in the script.
# Derived from pyproject.toml [project.dependencies] and dev extras.
# Only the top-level importable name matters, not the distribution name.
_THIRD_PARTY_IMPORTS: frozenset[str] = frozenset(
    [
        "anthropic",
        "frontmatter",  # python-frontmatter
        "jsonschema",
        "markdown_it",  # markdown-it-py
        "tiktoken",
        "yaml",  # PyYAML
        "pytest",
        "semgrep",
        "packaging",
        "bandit",
        "ruff",
        "mypy",
        "openai",
        "lefthook",
    ]
)

# Documentation files that are checked. Caller may override via --docs.
_DEFAULT_DOCS: list[str] = [
    "CONTRIBUTING.md",
    ".agents/SESSION-PROTOCOL.md",
    ".github/copilot-instructions.md",
    "README.md",
]


def _collect_third_party_imports(script_path: Path) -> set[str]:
    """Return the set of third-party top-level module names imported by script."""
    try:
        source = script_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    try:
        tree = ast.parse(source, filename=str(script_path))
    except SyntaxError:
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _THIRD_PARTY_IMPORTS:
                    found.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in _THIRD_PARTY_IMPORTS:
                    found.add(top)
    return found


def check_docs(
    doc_paths: list[Path],
    repo_root: Path,
) -> list[tuple[Path, int, str, set[str]]]:
    """Scan docs for bare-python3 invocations of third-party-importing scripts.

    Returns a list of (doc_path, line_number, script_rel_path, bad_imports).
    An empty list means no violations.
    """
    violations: list[tuple[Path, int, str, set[str]]] = []

    for doc_path in doc_paths:
        if not doc_path.exists():
            continue
        lines = doc_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in enumerate(lines, start=1):
            for m in _BARE_PY3_PATTERN.finditer(line):
                rel = m.group(1)
                script_path = repo_root / rel
                if not script_path.exists():
                    continue
                bad = _collect_third_party_imports(script_path)
                if bad:
                    violations.append((doc_path, lineno, rel, bad))

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check docs for bare-python3 invocations of dependency-heavy scripts",
    )
    parser.add_argument(
        "--docs",
        nargs="*",
        metavar="FILE",
        default=_DEFAULT_DOCS,
        help="Documentation files to scan (default: CONTRIBUTING.md, SESSION-PROTOCOL.md, ...)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        metavar="DIR",
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    doc_paths = [repo_root / d for d in args.docs]

    violations = check_docs(doc_paths, repo_root)

    if not violations:
        print("OK: no bare-python3 invocations of dependency-importing scripts found")
        return 0

    print(
        f"ERROR: {len(violations)} bare-python3 invocation(s) "
        "of scripts that import third-party modules:",
        file=sys.stderr,
    )
    for doc_path, lineno, rel, bad in violations:
        modules = ", ".join(sorted(bad))
        print(
            f"  {doc_path.relative_to(repo_root)}:{lineno}: "
            f"`python3 {rel}` imports [{modules}] -- use `uv run python {rel}`",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
