#!/usr/bin/env python3
"""Validate ``argument-hint`` YAML frontmatter values.

Copilot CLI's command loader is stricter than PyYAML for bracket-bearing
``argument-hint`` values. PyYAML accepts some unquoted hints as strings, while
the loader can interpret adjacent ``[...]`` groups as flow nodes and fail at
load time. PyYAML also parses an unquoted ``[VALUE]`` hint as a sequence, not a
string. This gate blocks both shapes before they ship.

Exit codes follow ADR-035:
    0 - All scanned argument-hint values are safe strings
    1 - One or more argument-hint values are unsafe
    2 - Config error
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]

_DEFAULT_PATTERNS = (
    ".claude/commands/**/*.md",
    ".github/prompts/**/*.md",
    "**/SKILL.md",
    "src/copilot-cli/**/*.md",
)
_MARKDOWN_SUFFIXES = (".md", ".mdx")
_GLOB_CHARS = "*?["


@dataclass(frozen=True, slots=True)
class ArgumentHintViolation:
    """A single unsafe ``argument-hint`` value."""

    path: Path
    line: int
    column: int
    value: str
    reason: str

    @property
    def suggestion(self) -> str:
        return f"argument-hint: '{_single_quote_text(self.value)}'"


def _single_quote_text(value: str) -> str:
    """Return text safe for a YAML single-quoted scalar."""

    return value.replace("'", "''")


def _raw_frontmatter_lines(text: str) -> list[str] | None:
    """Return frontmatter lines without fences, or None when absent."""

    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            return lines[1:index]
    return None


def _is_quoted_scalar(raw_value: str) -> bool:
    stripped = raw_value.strip()
    return len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}


def _strip_inline_comment(raw_value: str) -> str:
    """Return ``raw_value`` without a trailing YAML comment."""

    quote: str | None = None
    first_scalar_index = len(raw_value) - len(raw_value.lstrip())
    index = 0
    while index < len(raw_value):
        char = raw_value[index]
        if quote is None:
            if index == first_scalar_index and char in {"'", '"'}:
                quote = char
            elif char == "#" and (index == 0 or raw_value[index - 1].isspace()):
                return raw_value[:index].strip()
        elif char == quote:
            if quote == "'" and index + 1 < len(raw_value) and raw_value[index + 1] == "'":
                index += 1
            else:
                quote = None
        index += 1
    return raw_value.strip()


def _parsed_argument_hint(raw_value: str) -> object:
    """Parse one ``argument-hint`` value as YAML."""

    return yaml.safe_load(f"argument-hint: {raw_value}").get("argument-hint")


def _has_unbalanced_square_brackets(value: str) -> bool:
    depth = 0
    for char in value:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def _argument_hint_error(raw_value: str) -> tuple[str, str] | None:
    """Return ``(reason, intended_value)`` for an unsafe hint."""

    stripped = _strip_inline_comment(raw_value)
    try:
        parsed = _parsed_argument_hint(stripped)
    except yaml.YAMLError as exc:
        return (
            f"invalid YAML argument-hint scalar: {str(exc).replace(chr(10), ' ').strip()}",
            stripped,
        )

    if not isinstance(parsed, str):
        return (
            f"argument-hint must be a string scalar, but YAML parsed {type(parsed).__name__}",
            stripped,
        )

    if _has_unbalanced_square_brackets(parsed):
        return ("argument-hint contains unbalanced square brackets", parsed)

    if not _is_quoted_scalar(stripped) and "] [" in parsed:
        return (
            "unquoted argument-hint contains adjacent bracket groups that "
            "Copilot CLI can parse as flow nodes",
            parsed,
        )

    return None


def find_argument_hint_violations(paths: list[Path]) -> list[ArgumentHintViolation]:
    """Return every unsafe ``argument-hint`` in the supplied markdown files."""

    violations: list[ArgumentHintViolation] = []
    for path in sorted(set(paths)):
        if not path.is_file():
            continue
        frontmatter_lines = _raw_frontmatter_lines(path.read_text(encoding="utf-8"))
        if frontmatter_lines is None:
            continue
        for offset, line in enumerate(frontmatter_lines, start=2):
            if not line.startswith("argument-hint:"):
                continue
            prefix, separator, raw_value = line.partition(":")
            if separator != ":" or prefix.strip() != "argument-hint":
                continue
            error = _argument_hint_error(raw_value)
            if error is None:
                continue
            reason, intended_value = error
            value_column = line.index(raw_value) + len(raw_value) - len(raw_value.lstrip()) + 1
            violations.append(
                ArgumentHintViolation(
                    path=path,
                    line=offset,
                    column=value_column,
                    value=intended_value,
                    reason=reason,
                )
            )
    return violations


def _matches_default_scan(path: Path) -> bool:
    normalized = path.as_posix()
    return (
        (normalized.startswith(".claude/commands/") and path.suffix in _MARKDOWN_SUFFIXES)
        or (normalized.startswith(".github/prompts/") and path.suffix in _MARKDOWN_SUFFIXES)
        or path.name == "SKILL.md"
        or (normalized.startswith("src/copilot-cli/") and path.suffix in _MARKDOWN_SUFFIXES)
    )


def _git_tracked_files(repo_root: Path) -> list[Path] | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [repo_root / line for line in result.stdout.splitlines() if line]


def _default_scan_paths(repo_root: Path) -> list[Path]:
    tracked = _git_tracked_files(repo_root)
    if tracked is not None:
        return [path for path in tracked if _matches_default_scan(path.relative_to(repo_root))]

    paths: set[Path] = set()
    for pattern in _DEFAULT_PATTERNS:
        paths.update(repo_root.glob(pattern))
    return sorted(paths)


def _resolve_target(repo_root: Path, target: str) -> list[Path]:
    candidate = Path(target)
    if any(char in target for char in _GLOB_CHARS):
        return sorted(repo_root.glob(target))

    path = candidate if candidate.is_absolute() else repo_root / candidate
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.suffix in _MARKDOWN_SUFFIXES)
    if path.exists():
        return [path]
    raise FileNotFoundError(target)


def collect_scan_paths(repo_root: Path, targets: list[str]) -> list[Path]:
    """Collect markdown files to scan."""

    if not targets:
        return _default_scan_paths(repo_root)

    paths: set[Path] = set()
    for target in targets:
        paths.update(_resolve_target(repo_root, target))
    return sorted(path for path in paths if path.suffix in _MARKDOWN_SUFFIXES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate bracket-safe YAML argument-hint frontmatter values.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Optional file, directory, or glob target(s). Defaults to command and skill markdown.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(_REPO_ROOT),
        help="Repository root for resolving relative targets.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"[FAIL] repository root not found: {repo_root}", file=sys.stderr)
        return 2

    try:
        paths = collect_scan_paths(repo_root, args.targets)
    except FileNotFoundError as exc:
        print(f"[FAIL] target not found: {exc}", file=sys.stderr)
        return 2

    violations = find_argument_hint_violations(paths)
    if violations:
        print(f"[FAIL] {len(violations)} unsafe argument-hint value(s) found:")
        for violation in violations:
            print(f"  - {violation.path}:{violation.line}:{violation.column}: {violation.reason}")
            print(f"    Fix: {violation.suggestion}")
        return 1

    print(f"[PASS] All argument-hint values are safe strings in {len(paths)} scanned file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
