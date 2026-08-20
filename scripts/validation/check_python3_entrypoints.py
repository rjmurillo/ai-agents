#!/usr/bin/env python3
"""Detect bare-python3 documentation pointing to scripts that import third-party deps.

A script that uses `import yaml`, `import anthropic`, or any other declared
dependency cannot be invoked as `python3 scripts/X.py` on a clean system: the
bare interpreter resolves only stdlib. Any such invocation must use
`uv run --frozen python scripts/X.py`.

This validator scans a configurable list of documentation files for
`python3 scripts/` patterns, then AST-checks each referenced script for
direct or transitive third-party imports, and fails if any mismatch is found.

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
    ".github/copilot-instructions.md",
    "README.md",
    ".agents/prototypes/agents/implementer.compressed.md",
    ".claude/agents/retrospective.md",
    ".github/agents/retrospective.agent.md",
    "src/claude/retrospective.md",
    "src/copilot-cli/agents/retrospective.agent.md",
    "src/vs-code-agents/retrospective.agent.md",
    "templates/agents/retrospective.shared.md",
]


def _parse_script(script_path: Path) -> ast.AST | None:
    """Parse a Python file, returning None when it cannot be inspected."""
    try:
        source = script_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    try:
        return ast.parse(source, filename=str(script_path))
    except SyntaxError:
        return None


def _candidate_module_files(
    base_path: Path,
    repo_root: Path,
) -> set[Path]:
    """Return a local import target and its package initializers."""
    leaf_candidates = {
        base_path.with_suffix(".py"),
        base_path / "__init__.py",
    }
    resolved_leaf = {
        candidate.resolve()
        for candidate in leaf_candidates
        if candidate.resolve().is_relative_to(repo_root)
        and candidate.resolve().is_file()
    }
    if not resolved_leaf:
        return set()

    relative_parts = base_path.relative_to(repo_root).parts
    package_initializers = {
        repo_root.joinpath(*relative_parts[:index], "__init__.py").resolve()
        for index in range(1, len(relative_parts))
    }
    return resolved_leaf | {
        initializer
        for initializer in package_initializers
        if initializer.is_file()
    }


def _absolute_import_bases(
    module_name: str,
    script_path: Path,
    repo_root: Path,
) -> list[Path]:
    """Resolve absolute imports from script and repository roots."""
    module_parts = module_name.split(".")
    return [
        script_path.parent.joinpath(*module_parts),
        repo_root.joinpath(*module_parts),
    ]


def _relative_import_base(
    node: ast.ImportFrom,
    script_path: Path,
    repo_root: Path,
) -> Path | None:
    """Resolve the package base for a relative import."""
    try:
        package_parts = script_path.parent.relative_to(repo_root).parts
    except ValueError:
        return None

    parent_count = node.level - 1
    if parent_count > len(package_parts):
        return None

    retained_parts = package_parts[: len(package_parts) - parent_count]
    module_parts = node.module.split(".") if node.module else []
    return repo_root.joinpath(*retained_parts, *module_parts)


def _local_import_paths(
    node: ast.Import | ast.ImportFrom,
    script_path: Path,
    repo_root: Path,
) -> set[Path]:
    """Resolve repository-local files imported by one AST node."""
    bases: list[Path] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            bases.extend(
                _absolute_import_bases(alias.name, script_path, repo_root)
            )
    elif node.level:
        relative_base = _relative_import_base(node, script_path, repo_root)
        if relative_base is not None:
            bases.append(relative_base)
            bases.extend(
                relative_base.joinpath(*alias.name.split("."))
                for alias in node.names
            )
    elif node.module:
        bases.extend(
            _absolute_import_bases(node.module, script_path, repo_root)
        )
        bases.extend(
            base.joinpath(*alias.name.split("."))
            for base in list(bases)
            for alias in node.names
        )

    local_paths: set[Path] = set()
    for base in bases:
        resolved_base = base.resolve()
        if resolved_base.is_relative_to(repo_root):
            local_paths.update(
                _candidate_module_files(resolved_base, repo_root)
            )
    return local_paths


def _collect_imports_recursive(
    script_path: Path,
    repo_root: Path,
    visited: set[Path],
) -> set[str]:
    """Collect third-party imports through repository-local dependencies."""
    resolved_script = script_path.resolve()
    if resolved_script in visited:
        return set()
    visited.add(resolved_script)

    tree = _parse_script(resolved_script)
    if tree is None:
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

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for local_path in _local_import_paths(
                node,
                resolved_script,
                repo_root,
            ):
                found.update(
                    _collect_imports_recursive(local_path, repo_root, visited)
                )
    return found


def _collect_third_party_imports(
    script_path: Path,
    repo_root: Path | None = None,
) -> set[str]:
    """Return direct and transitive third-party imports for a script."""
    resolved_root = (repo_root or script_path.parent).resolve()
    return _collect_imports_recursive(script_path, resolved_root, set())


def check_docs(
    doc_paths: list[Path],
    repo_root: Path,
) -> list[tuple[Path, int, str, set[str]]]:
    """Scan docs for bare-python3 invocations of third-party-importing scripts.

    Returns a list of (doc_path, line_number, script_rel_path, bad_imports).
    An empty list means no violations.

    Raises OSError when a listed doc exists but cannot be read (a directory
    passed as a doc, a permission denial). ``main`` maps that to exit code 2
    per the module contract; the scanner itself does not swallow it, because a
    doc that was never scanned is not a doc that passed.
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
                bad = _collect_third_party_imports(script_path, repo_root)
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
        help="Documentation files to scan (default: CONTRIBUTING.md, copilot-instructions.md, ...)",
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

    try:
        violations = check_docs(doc_paths, repo_root)
    except OSError as exc:
        print(f"ERROR: cannot read documentation file: {exc}", file=sys.stderr)
        return 2

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
            f"`python3 {rel}` imports [{modules}] -- "
            f"use `uv run --frozen python {rel}`",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
