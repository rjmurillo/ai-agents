#!/usr/bin/env python3
"""Pure-Python markdown verifier -- stdlib only, no ambient imports.

Implements the subset of markdownlint rules enabled in
``markdownlint-safe-config.yaml`` using only the Python standard library.
The YAML config is the documentation; this module is the enforcement.

Supported rules (matching the safe config):
    MD004  Unordered list style (dash only)
    MD024  No duplicate sibling headings
    MD025  Single top-level heading (H1)
    MD033  No inline HTML except allowed elements
    MD040  Fenced code blocks require a language
    MD041  First line in file should be a top-level heading
    MD046  Code block style (fenced only)

Disabled rules (per safe config): MD003, MD013, MD018, MD029,
MD048, MD049, MD050, MD060.

Override rules (per safe config):
    .claude/skills/** and src/copilot-cli/skills/** disable MD040, MD033.

Interface:
    python _markdownlint_verifier.py --markdown-lint-only -- <file> [<file>...]

Exit codes:
    0 = All files clean.
    1 = One or more violations found.
    2 = Infrastructure / argument error.
"""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatch
from pathlib import PurePosixPath

# ---------------------------------------------------------------------------
# Immutable config (mirrors markdownlint-safe-config.yaml)
# ---------------------------------------------------------------------------

# Files matching any of these globs are skipped entirely.
_IGNORE_GLOBS: tuple[str, ...] = (
    ".git/**", "**/node_modules/**", ".venv/**", ".mypy_cache/**",
    ".pytest_cache/**", ".pytest_tmp/**", ".ruff_cache/**",
    "ai_agents.egg-info/**", "dist/**", ".claude/worktrees/**",
    "worktree-*/**", "worktree--/**", "wt_*/**", ".wt/**",
    ".worktrees/**", ".work-*/**", ".agents/**", ".serena/**",
    ".claude-mem/**", ".forgetful/**", ".diffray/**", ".flowbaby/**",
    ".factory/**", ".codeql/**", ".baseline/**", ".gemini/**",
    ".vscode/**", ".config/**", "tmp/**", "**/*.ps1", "**/*.psm1",
    "src/claude/claude-instructions.template.md",
    "src/vs-code-agents/copilot-instructions.md",
    "src/copilot-cli/docs/copilot-instructions.md",
    "docs/autonomous-pr-monitor.md",
    "docs/autonomous-issue-development.md",
    ".github/agents/**/*.agent.md",
    "**/CLAUDE.md",
    ".claude/commands/spec.md", ".claude/commands/plan.md",
    ".claude/commands/build.md", ".claude/commands/test.md",
    ".claude/commands/ship.md",
    "src/copilot-cli/skills/spec/SKILL.md",
    "src/copilot-cli/skills/plan/SKILL.md",
    "src/copilot-cli/skills/build/SKILL.md",
    "src/copilot-cli/skills/test/SKILL.md",
    "src/copilot-cli/skills/ship/SKILL.md",
    ".claude/skills/spec-generator/references/spec-step0-gates.md",
    ".claude/skills/spec-generator/references/spec-prior-art-schema.md",
    "src/copilot-cli/skills/spec-generator/references/spec-step0-gates.md",
    "src/copilot-cli/skills/spec-generator/references/spec-prior-art-schema.md",
    ".claude/skills/cva-analysis/references/SKILL_SPEC.md",
    "src/copilot-cli/skills/cva-analysis/references/SKILL_SPEC.md",
)

# Globs where MD040 and MD033 are disabled (skill trees).
_SKILL_OVERRIDE_GLOBS: tuple[str, ...] = (
    ".claude/skills/**",
    "src/copilot-cli/skills/**",
)

# MD033 allowed HTML elements.
_MD033_ALLOWED: frozenset[str] = frozenset({
    "br", "code", "kbd", "sup", "sub",
    "details", "summary", "strong", "example",
})

# Regex patterns compiled once.
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
_RE_FENCE_OPEN = re.compile(r"^(\s*)(```+|~~~+)(.*)")
_RE_FENCE_CLOSE = re.compile(r"^(\s*)(```+|~~~+)\s*$")
_RE_LIST_MARKER = re.compile(r"^(\s*)([*+-])\s")
_RE_HTML_TAG = re.compile(r"<(/?)(\w+)[\s/>]")
_RE_FRONTMATTER_OPEN = re.compile(r"^---\s*$")
_RE_FRONTMATTER_CLOSE = re.compile(r"^(---|\.\.\.)\s*$")


def _matches_any_glob(path: str, globs: tuple[str, ...]) -> bool:
    """Return True if *path* matches any of the glob patterns."""
    posix = PurePosixPath(path).as_posix()
    for g in globs:
        if fnmatch(posix, g):
            return True
        # fnmatch doesn't handle ** well; also try matching the
        # basename against the tail of the glob.
        if "**" in g:
            # Convert ** glob to a simple prefix + suffix check.
            prefix, _, suffix = g.partition("**")
            if prefix and not posix.startswith(prefix.rstrip("/")):
                continue
            tail = suffix.lstrip("/")
            if tail and fnmatch(posix.split("/")[-1], tail):
                return True
            if not tail and posix.startswith(prefix.rstrip("/")):
                return True
    return False


def _skip_frontmatter(lines: list[str]) -> int:
    """Return the index of the first content line (past YAML front matter)."""
    if not lines:
        return 0
    if _RE_FRONTMATTER_OPEN.match(lines[0]):
        for i in range(1, len(lines)):
            if _RE_FRONTMATTER_CLOSE.match(lines[i]):
                return i + 1
    return 0


# ---------------------------------------------------------------------------
# Individual rule checkers.  Each returns a list of ``(line_no, message)``
# tuples (1-based line numbers).
# ---------------------------------------------------------------------------

def _check_md041(
    lines: list[str], start: int,
) -> list[tuple[int, str]]:
    """MD041: First line should be a top-level heading."""
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        m = _RE_HEADING.match(stripped)
        if m and len(m.group(1)) == 1:
            return []
        return [(i + 1, "MD041 First line in file should be a top-level heading")]
    return []


def _check_md025(lines: list[str]) -> list[tuple[int, str]]:
    """MD025: Multiple top-level headings."""
    in_fence = False
    h1_count = 0
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _RE_FENCE_OPEN.match(line) and not in_fence:
            in_fence = True
            continue
        if in_fence and _RE_FENCE_CLOSE.match(line):
            in_fence = False
            continue
        if in_fence:
            continue
        m = _RE_HEADING.match(line)
        if m and len(m.group(1)) == 1:
            h1_count += 1
            if h1_count > 1:
                violations.append(
                    (i + 1, "MD025 Multiple top-level headings in the same document")
                )
    return violations


def _check_md024(lines: list[str]) -> list[tuple[int, str]]:
    """MD024: No duplicate heading text (siblings_only=true)."""
    in_fence = False
    # Track headings in a tree: stack of (level, {texts_at_this_level})
    # We maintain parent contexts; siblings share a parent.
    stack: list[tuple[int, set[str]]] = []
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _RE_FENCE_OPEN.match(line) and not in_fence:
            in_fence = True
            continue
        if in_fence and _RE_FENCE_CLOSE.match(line):
            in_fence = False
            continue
        if in_fence:
            continue
        m = _RE_HEADING.match(line)
        if not m:
            continue
        level = len(m.group(1))
        text = m.group(2).strip()
        # Pop stack entries deeper than or equal to current level.
        while stack and stack[-1][0] >= level:
            stack.pop()
        # Check siblings: children of current top of stack.
        if stack:
            parent_children = stack[-1][1]
        else:
            # Top-level headings are siblings of root.
            if not stack:
                stack.append((0, set()))
            parent_children = stack[-1][1]
        if text in parent_children:
            violations.append(
                (i + 1, f"MD024 Multiple headings with the same content: '{text}'")
            )
        parent_children.add(text)
        # Push this heading as potential parent for deeper headings.
        stack.append((level, set()))
    return violations


def _check_md040(lines: list[str]) -> list[tuple[int, str]]:
    """MD040: Fenced code blocks should have a language specified."""
    in_fence = False
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _RE_FENCE_OPEN.match(line)
        if m and not in_fence:
            in_fence = True
            info = m.group(3).strip()
            if not info:
                violations.append(
                    (i + 1, "MD040 Fenced code blocks should have a language specified")
                )
            continue
        if in_fence and _RE_FENCE_CLOSE.match(line):
            in_fence = False
    return violations


def _check_md004(lines: list[str]) -> list[tuple[int, str]]:
    """MD004: Unordered list style must be dash."""
    in_fence = False
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _RE_FENCE_OPEN.match(line) and not in_fence:
            in_fence = True
            continue
        if in_fence and _RE_FENCE_CLOSE.match(line):
            in_fence = False
            continue
        if in_fence:
            continue
        m = _RE_LIST_MARKER.match(line)
        if m and m.group(2) != "-":
            violations.append(
                (i + 1, f"MD004 Unordered list style: expected '-', found '{m.group(2)}'")
            )
    return violations


def _check_md033(lines: list[str]) -> list[tuple[int, str]]:
    """MD033: Inline HTML restricted to allowed elements."""
    in_fence = False
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _RE_FENCE_OPEN.match(line) and not in_fence:
            in_fence = True
            continue
        if in_fence and _RE_FENCE_CLOSE.match(line):
            in_fence = False
            continue
        if in_fence:
            continue
        for tag_match in _RE_HTML_TAG.finditer(line):
            tag_name = tag_match.group(2).lower()
            if tag_name not in _MD033_ALLOWED:
                violations.append(
                    (i + 1, f"MD033 Inline HTML: element '{tag_name}' not allowed")
                )
    return violations


def _check_md046(lines: list[str]) -> list[tuple[int, str]]:
    """MD046: Code block style must be fenced (not indented)."""
    in_fence = False
    in_list = False
    violations: list[tuple[int, str]] = []
    prev_blank = True
    for i, line in enumerate(lines):
        if _RE_FENCE_OPEN.match(line) and not in_fence:
            in_fence = True
            continue
        if in_fence and _RE_FENCE_CLOSE.match(line):
            in_fence = False
            prev_blank = False
            continue
        if in_fence:
            continue
        stripped = line.rstrip()
        # Track list context (indented code in lists is normal content).
        if _RE_LIST_MARKER.match(line):
            in_list = True
            prev_blank = False
            continue
        if not stripped:
            prev_blank = True
            if in_list and not line.startswith(" "):
                in_list = False
            continue
        # Indented code block: 4+ spaces after a blank line, not in a list.
        if (
            prev_blank
            and not in_list
            and len(line) > 4
            and line[:4] == "    "
            and line[4:5] not in (" ", "\t")
        ):
            violations.append(
                (i + 1, "MD046 Code block style: expected fenced, found indented")
            )
        prev_blank = False
    return violations


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def lint_file(
    path: str, *, skip_md040: bool = False, skip_md033: bool = False,
) -> list[str]:
    """Lint a single file. Return list of diagnostic strings."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]

    lines = text.splitlines()
    start = _skip_frontmatter(lines)

    violations: list[tuple[int, str]] = []
    violations.extend(_check_md041(lines, start))
    violations.extend(_check_md025(lines))
    violations.extend(_check_md024(lines))
    violations.extend(_check_md004(lines))
    violations.extend(_check_md046(lines))
    if not skip_md040:
        violations.extend(_check_md040(lines))
    if not skip_md033:
        violations.extend(_check_md033(lines))

    return [f"{path}:{line}: {msg}" for line, msg in sorted(violations)]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--markdown-lint-only" not in args:
        print(
            "usage: _markdownlint_verifier.py --markdown-lint-only -- <files>",
            file=sys.stderr,
        )
        return 2
    try:
        sep_idx = args.index("--")
    except ValueError:
        print("missing -- separator", file=sys.stderr)
        return 2

    files = args[sep_idx + 1:]
    if not files:
        return 0

    all_violations: list[str] = []
    for fpath in files:
        # Apply ignores.
        if _matches_any_glob(fpath, _IGNORE_GLOBS):
            continue
        # Apply skill-tree overrides.
        in_skills = _matches_any_glob(fpath, _SKILL_OVERRIDE_GLOBS)
        violations = lint_file(
            fpath, skip_md040=in_skills, skip_md033=in_skills,
        )
        all_violations.extend(violations)

    if all_violations:
        for v in all_violations:
            print(v, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
