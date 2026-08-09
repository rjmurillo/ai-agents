#!/usr/bin/env python3
"""Pure-Python markdownlint-compatible verifier -- stdlib only.

Implements a CommonMark-aware block parser followed by rule checks.
Handles blockquote nesting, setext headings, indented/fenced code blocks,
and list markers faithfully.

Supported rules (default-enabled per markdownlint + safe config):
    MD004  Unordered list style (dash only)
    MD024  No duplicate sibling headings (siblings_only)
    MD025  Single top-level heading (H1)
    MD033  No inline HTML except allowed elements
    MD040  Fenced code blocks require a language
    MD041  First line should be a top-level heading
    MD046  Code block style (fenced only)

Disabled by config: MD003, MD013, MD018, MD029, MD048, MD049, MD050, MD060.

Override: .claude/skills/** and src/copilot-cli/skills/** disable MD040/MD033.

Interface:
    python _markdownlint_verifier.py --markdown-lint-only -- <file>...

Exit codes:
    0 = All files clean (or no files).
    1 = Violations found.
    2 = Infrastructure / argument error.
"""

from __future__ import annotations

import re
import sys
from fnmatch import fnmatch
from pathlib import PurePosixPath
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Immutable config (mirrors markdownlint-safe-config.yaml)
# ---------------------------------------------------------------------------

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

_SKILL_OVERRIDE_GLOBS: tuple[str, ...] = (
    ".claude/skills/**",
    "src/copilot-cli/skills/**",
)

_MD033_ALLOWED: frozenset[str] = frozenset({
    "br", "code", "kbd", "sup", "sub",
    "details", "summary", "strong", "example",
})

# ---------------------------------------------------------------------------
# Block parser types
# ---------------------------------------------------------------------------


class Heading(NamedTuple):
    line: int  # 1-based
    level: int  # 1-6
    text: str
    in_blockquote: bool


class FenceOpen(NamedTuple):
    line: int
    info: str  # language tag (may be empty)
    in_blockquote: bool


class ListItem(NamedTuple):
    line: int
    marker: str  # '-', '*', '+'
    in_blockquote: bool


class HtmlTag(NamedTuple):
    line: int
    tag: str
    in_blockquote: bool


class IndentedCode(NamedTuple):
    line: int
    in_blockquote: bool


# Regex patterns
_RE_ATX = re.compile(r"^(#{1,6})(?:\s+(.*))?$")
_RE_SETEXT_H1 = re.compile(r"^=+\s*$")
_RE_SETEXT_H2 = re.compile(r"^-+\s*$")
_RE_FENCE = re.compile(r"^(`{3,}|~{3,})(.*)")
_RE_LIST = re.compile(r"^(\s*)([*+-])\s")
_RE_HTML = re.compile(r"<(/?)(\w+)[\s/>]")
_RE_BQ = re.compile(r"^(>\s?)")
_RE_FRONTMATTER = re.compile(r"^---\s*$")


def _strip_blockquote(line: str) -> tuple[str, bool]:
    """Strip one level of blockquote prefix. Return (content, was_quoted)."""
    m = _RE_BQ.match(line)
    if m:
        return line[m.end():], True
    return line, False


def _strip_all_blockquotes(line: str) -> tuple[str, int]:
    """Strip all blockquote levels. Return (content, depth)."""
    depth = 0
    while True:
        content, was_quoted = _strip_blockquote(line)
        if not was_quoted:
            break
        line = content
        depth += 1
    return line, depth


# ---------------------------------------------------------------------------
# Block-level parser
# ---------------------------------------------------------------------------

def _parse_blocks(lines: list[str]) -> tuple[
    list[Heading],
    list[FenceOpen],
    list[ListItem],
    list[HtmlTag],
    list[IndentedCode],
    int,  # first content line (past frontmatter), 0-based
]:
    """Parse markdown into block-level elements."""
    headings: list[Heading] = []
    fences: list[FenceOpen] = []
    list_items: list[ListItem] = []
    html_tags: list[HtmlTag] = []
    indented_codes: list[IndentedCode] = []

    # Skip frontmatter
    start = 0
    if lines and _RE_FRONTMATTER.match(lines[0]):
        for i in range(1, len(lines)):
            if re.match(r"^(---|\.\.\.)(\s*)$", lines[i]):
                start = i + 1
                break

    in_fence = False
    fence_char = ""
    fence_count = 0
    fence_bq_depth = 0
    prev_line_text = ""
    prev_line_blank = True
    in_list = False

    for i in range(start, len(lines)):
        raw_line = lines[i]
        content, bq_depth = _strip_all_blockquotes(raw_line)
        in_bq = bq_depth > 0

        # --- Fenced code block tracking ---
        if in_fence:
            # Close fence: same char, at least same count, same bq depth
            if bq_depth == fence_bq_depth:
                m = _RE_FENCE.match(content)
                if m:
                    c = m.group(1)[0]
                    cnt = len(m.group(1))
                    if c == fence_char and cnt >= fence_count and not m.group(2).strip():
                        in_fence = False
            prev_line_text = ""
            prev_line_blank = False
            continue

        # Check for fence open
        m = _RE_FENCE.match(content)
        if m:
            fence_char = m.group(1)[0]
            fence_count = len(m.group(1))
            fence_bq_depth = bq_depth
            info = m.group(2).strip()
            fences.append(FenceOpen(line=i + 1, info=info, in_blockquote=in_bq))
            in_fence = True
            prev_line_text = ""
            prev_line_blank = False
            continue

        stripped = content.rstrip()

        # --- Setext heading detection ---
        # A setext heading is a paragraph line followed by === or ---
        if prev_line_text and not prev_line_blank:
            if _RE_SETEXT_H1.match(stripped):
                headings.append(Heading(
                    line=i,  # prev line is the heading text
                    level=1,
                    text=prev_line_text.strip(),
                    in_blockquote=in_bq,
                ))
                prev_line_text = ""
                prev_line_blank = False
                continue
            if _RE_SETEXT_H2.match(stripped) and not _RE_LIST.match(content):
                headings.append(Heading(
                    line=i,
                    level=2,
                    text=prev_line_text.strip(),
                    in_blockquote=in_bq,
                ))
                prev_line_text = ""
                prev_line_blank = False
                continue

        # --- ATX heading ---
        m_atx = _RE_ATX.match(stripped)
        if m_atx:
            level = len(m_atx.group(1))
            text = (m_atx.group(2) or "").rstrip("#").strip()
            headings.append(Heading(
                line=i + 1, level=level, text=text, in_blockquote=in_bq,
            ))
            prev_line_text = ""
            prev_line_blank = False
            continue

        # --- List items ---
        m_list = _RE_LIST.match(content)
        if m_list:
            list_items.append(ListItem(
                line=i + 1, marker=m_list.group(2), in_blockquote=in_bq,
            ))
            in_list = True
            prev_line_text = stripped
            prev_line_blank = False
            continue

        # --- Indented code block ---
        if (
            prev_line_blank
            and not in_list
            and len(content) > 4
            and content[:4] == "    "
            and content[4:5] not in ("", " ", "\t")
        ):
            indented_codes.append(IndentedCode(line=i + 1, in_blockquote=in_bq))
            prev_line_text = ""
            prev_line_blank = False
            continue

        # --- HTML tags (inline check) ---
        for tag_match in _RE_HTML.finditer(content):
            tag_name = tag_match.group(2).lower()
            html_tags.append(HtmlTag(line=i + 1, tag=tag_name, in_blockquote=in_bq))

        # Track blank/text state
        if not stripped:
            prev_line_blank = True
            if in_list:
                in_list = False
            prev_line_text = ""
        else:
            prev_line_blank = False
            prev_line_text = stripped

    return headings, fences, list_items, html_tags, indented_codes, start


# ---------------------------------------------------------------------------
# Rule checkers
# ---------------------------------------------------------------------------

def _check_md041(
    headings: list[Heading], lines: list[str], start: int,
) -> list[tuple[int, str]]:
    """MD041: First line should be a top-level heading."""
    # Find first non-blank content line
    for i in range(start, len(lines)):
        content, _ = _strip_all_blockquotes(lines[i])
        if content.strip():
            # Check if the first heading is H1 and appears at/before this line
            for h in headings:
                if h.level == 1 and h.line <= i + 1:
                    return []
            return [(i + 1, "MD041 First line in file should be a top-level heading")]
    return []


def _check_md025(headings: list[Heading]) -> list[tuple[int, str]]:
    """MD025: Multiple top-level headings."""
    h1_count = 0
    violations: list[tuple[int, str]] = []
    for h in headings:
        if h.level == 1:
            h1_count += 1
            if h1_count > 1:
                violations.append((
                    h.line,
                    "MD025 Multiple top-level headings in the same document",
                ))
    return violations


def _check_md024(headings: list[Heading]) -> list[tuple[int, str]]:
    """MD024: No duplicate heading text (siblings_only=true)."""
    # Build heading tree: track siblings under each parent
    stack: list[tuple[int, set[str]]] = [(0, set())]  # root
    violations: list[tuple[int, str]] = []
    for h in headings:
        level = h.level
        # Pop deeper/equal levels
        while stack and stack[-1][0] >= level:
            stack.pop()
        if not stack:
            stack.append((0, set()))
        parent_children = stack[-1][1]
        if h.text in parent_children:
            violations.append((
                h.line,
                f"MD024 Multiple headings with the same content: '{h.text}'",
            ))
        parent_children.add(h.text)
        stack.append((level, set()))
    return violations


def _check_md040(fences: list[FenceOpen]) -> list[tuple[int, str]]:
    """MD040: Fenced code blocks should have a language specified."""
    violations: list[tuple[int, str]] = []
    for f in fences:
        if not f.info:
            violations.append((
                f.line,
                "MD040 Fenced code blocks should have a language specified",
            ))
    return violations


def _check_md004(list_items: list[ListItem]) -> list[tuple[int, str]]:
    """MD004: Unordered list style must be dash."""
    violations: list[tuple[int, str]] = []
    for item in list_items:
        if item.marker != "-":
            violations.append((
                item.line,
                f"MD004 Unordered list style: expected '-', found '{item.marker}'",
            ))
    return violations


def _check_md033(html_tags: list[HtmlTag]) -> list[tuple[int, str]]:
    """MD033: Inline HTML restricted to allowed elements."""
    violations: list[tuple[int, str]] = []
    for tag in html_tags:
        if tag.tag not in _MD033_ALLOWED:
            violations.append((
                tag.line,
                f"MD033 Inline HTML: element '{tag.tag}' not allowed",
            ))
    return violations


def _check_md046(indented_codes: list[IndentedCode]) -> list[tuple[int, str]]:
    """MD046: Code block style must be fenced (not indented)."""
    violations: list[tuple[int, str]] = []
    for ic in indented_codes:
        violations.append((
            ic.line,
            "MD046 Code block style: expected fenced, found indented",
        ))
    return violations


# ---------------------------------------------------------------------------
# Glob matching
# ---------------------------------------------------------------------------

def _matches_any_glob(path: str, globs: tuple[str, ...]) -> bool:
    posix = PurePosixPath(path).as_posix()
    for g in globs:
        if fnmatch(posix, g):
            return True
        if "**" in g:
            prefix, _, suffix = g.partition("**")
            if prefix and not posix.startswith(prefix.rstrip("/")):
                continue
            tail = suffix.lstrip("/")
            if tail and fnmatch(posix.split("/")[-1], tail):
                return True
            if not tail and posix.startswith(prefix.rstrip("/")):
                return True
    return False


# ---------------------------------------------------------------------------
# Main
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
    if not lines:
        return []

    headings, fences, list_items, html_tags, indented_codes, start = _parse_blocks(lines)

    violations: list[tuple[int, str]] = []
    violations.extend(_check_md041(headings, lines, start))
    violations.extend(_check_md025(headings))
    violations.extend(_check_md024(headings))
    violations.extend(_check_md004(list_items))
    violations.extend(_check_md046(indented_codes))
    if not skip_md040:
        violations.extend(_check_md040(fences))
    if not skip_md033:
        violations.extend(_check_md033(html_tags))

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
        if _matches_any_glob(fpath, _IGNORE_GLOBS):
            continue
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
