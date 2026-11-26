"""Shared plumbing for gates that scan a rendered agent tree.

``check_agent_delegation.py``, ``check_agent_success_criterion.py``, and
``check_orchestrator_vocabulary.py`` all list an agent tree, read agent
frontmatter, skip fenced code, and expose the same ADR-035 CLI. This module
holds that code once, so the three gates agree on what a readable agent file
is and what counts as prose.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.hook_utilities.frontmatter_block import (
    FrontmatterStatus,
    parse_frontmatter,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


@dataclass(frozen=True)
class AgentText:
    """One agent file split into its frontmatter mapping and its body."""

    frontmatter: dict[str, object]
    body: str
    body_line_offset: int


def read_agent_text(text: str, *, allow_duplicate_keys: bool = True) -> AgentText:
    """Split agent text into frontmatter and body.

    Raises ``ValueError`` with a reason when the text has no frontmatter block,
    the block is not valid YAML, or it is not a mapping. With
    ``allow_duplicate_keys=False`` a repeated key at any depth is invalid YAML,
    so a second ``value:`` cannot hide the first. The delegation and
    vocabulary gates keep the permissive default they had before this module.
    ``body_line_offset`` is the number of lines before the body, so body line
    ``n`` is file line ``n + body_line_offset``.
    """
    result = parse_frontmatter(text, yaml, allow_duplicate_keys=allow_duplicate_keys)
    if not result.present or result.status is FrontmatterStatus.UNTERMINATED:
        raise ValueError("no YAML frontmatter block")
    if result.status is FrontmatterStatus.MALFORMED:
        detail = (result.error or "").removeprefix("invalid YAML frontmatter: ")
        raise ValueError(f"frontmatter is not valid YAML: {detail}")
    loaded = result.metadata
    if result.status is not FrontmatterStatus.VALID or not isinstance(loaded, dict):
        raise ValueError("frontmatter is not a mapping")
    # parse_frontmatter returns the body as a suffix of the text, so the
    # prefix length gives the line offset exactly.
    offset = text[: len(text) - len(result.body)].count("\n")
    return AgentText(frontmatter=loaded, body=result.body, body_line_offset=offset)


def prose_lines(body: str) -> tuple[list[tuple[int, str]], bool]:
    """Return ``(line_number, text)`` for body lines outside fenced code blocks.

    A fence closes on a marker of the same character that is at least as long
    as the opener, with nothing after it on the line. The second value is True
    when a fence is still open at the end of the body: every line after the
    opener was dropped, so a caller that treats the drop as "no prose" would
    pass content it never read.
    """
    kept: list[tuple[int, str]] = []
    opener = ""
    for number, line in enumerate(body.splitlines(), start=1):
        match = _FENCE.match(line)
        if opener:
            # A closing fence carries only spaces or tabs after it (CommonMark 4.5), so an
            # inner ```python line inside an open fence is content, not a close.
            closes = (
                match
                and match.group(1)[0] == opener[0]
                and len(match.group(1)) >= len(opener)
                and not line[match.end() :].strip(" \t")
            )
            if closes:
                opener = ""
            continue
        if match:
            opener = match.group(1)
            continue
        kept.append((number, line))
    return kept, bool(opener)


def agent_markdown_files(repo_root: Path, tree: Path) -> list[Path]:
    """Return the sorted ``*.md`` files directly under ``repo_root / tree``.

    Raises ``FileNotFoundError`` when the tree is absent or empty: a silently
    empty scan is a passing scan that proves nothing.
    """
    folder = repo_root / tree
    if not folder.is_dir():
        raise FileNotFoundError(f"agent tree not found: {folder}")
    files = sorted(folder.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"agent tree yields no Markdown files: {folder}")
    return files


def run_repo_gate(
    argv: Sequence[str] | None,
    validate: Callable[[Path], bool],
    required_tree: Path | None = None,
) -> int:
    """Run ``validate`` on the root named by ``argv[0]`` or this repository.

    Returns an ADR-035 exit code: 0 when ``validate`` passes, 1 when it fails,
    and 2 when the root is invalid or ``required_tree`` is missing under it.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else _REPO_ROOT
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if required_tree is not None and not (repo_root / required_tree).is_dir():
        print(f"[FAIL] Missing agent tree: {repo_root / required_tree}", file=sys.stderr)
        return 2
    return 0 if validate(repo_root) else 1
