"""Copilot SKILL.md projection keeps `allowed-tools` argument scoping (issue #5691).

ADR-107 section 5 invariant 6: a projection must preserve the authorization
requirements and the abstract capability set. For a skill that is the
`allowed-tools` frontmatter value.

The runtime probe in `probe-evidence.md` section 10 found that Copilot CLI
1.0.95 grants nothing from a skill's `allowed-tools`, scoped or bare. The
probe ran noninteractively (`-p --no-ask-user`), so it recorded denial, not a
prompt. Interactive behavior is unverified. The mirror is not wider than the
source in the probed mode. A future Copilot release could start reading the
tool name and dropping the argument, which is the widening
`tool-use-hook-bar.md` records for matchers. This predicate keeps the
repository side of that boundary shut: the generator may respell an MCP tool
name and nothing else, so a scoped entry such as `Bash(git push:*)` is never
degraded to bare `Bash` in the mirror. It compares source and mirror text
only. It cannot detect a Copilot upgrade that changes how permissions are
interpreted; rerun the probe in `probe-evidence.md` section 10 after upgrades.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

from copilot_body_translation import (  # noqa: E402
    respell_mcp_tool_names,
    translate_allowed_tools,
    translate_skill_file,
)

SOURCE_SKILLS = REPO_ROOT / ".claude" / "skills"
MIRROR_SKILLS = REPO_ROOT / "src" / "copilot-cli" / "skills"
_OUT = Path("/nonexistent/skills")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_ENTRY = re.compile(r"^([^()]+?)(?:\((.*)\))?$", re.DOTALL)
_PUSH_PR_LINE = (
    "Bash(git checkout -b:*), Bash(git add:*), Bash(git push:*), "
    "Bash(python3:-I */pr/new_pr.py*), Bash(mkdir:-p .agents/scratch), "
    "Edit(.agents/scratch/pr-body-*.md)"
)


def split_entries(value: str | list[str] | None) -> list[str]:
    """Split an `allowed-tools` value into entries, keeping commas inside parens."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    entries: list[str] = []
    depth = 0
    current = ""
    for char in value:
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            entries.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        entries.append(current.strip())
    return entries


def parse_entry(entry: str) -> tuple[str, str | None]:
    """Return (tool name, argument constraint or None) for one entry."""
    match = _ENTRY.match(entry)
    if match is None:
        raise ValueError(f"unparseable allowed-tools entry: {entry!r}")
    return match.group(1).strip(), match.group(2)


def invariant_6_violations(
    source: str | list[str] | None, projected: str | list[str] | None
) -> list[str]:
    """Return one message per way the projection weakens the source grant.

    The only legal difference is the MCP respelling of the tool name. Entry
    count, order, and every argument constraint must survive, and a scoped
    entry must never become a bare one.
    """
    src = split_entries(source)
    out = split_entries(projected)
    if len(src) != len(out):
        return [f"entry count {len(src)} became {len(out)}"]
    problems: list[str] = []
    for before, after in zip(src, out, strict=True):
        name, arg = parse_entry(before)
        new_name, new_arg = parse_entry(after)
        if arg is not None and new_arg is None:
            problems.append(f"{before!r} widened to bare {after!r}")
        elif arg != new_arg:
            problems.append(f"{before!r} argument changed to {after!r}")
        elif respell_mcp_tool_names(name) != new_name:
            problems.append(f"{before!r} renamed to {after!r}")
    return problems


def _allowed_tools(path: Path) -> str | list[str] | None:
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path} has no frontmatter"
    parsed = yaml.safe_load(match.group(1)) or {}
    return parsed.get("allowed-tools")


def _skills_with_allowed_tools() -> list[str]:
    return sorted(
        path.parent.name
        for path in SOURCE_SKILLS.glob("*/SKILL.md")
        if (MIRROR_SKILLS / path.parent.name / "SKILL.md").is_file()
        and _allowed_tools(path) is not None
    )


# Predicate: positive cases ---------------------------------------------------


def test_identical_scoped_grant_passes() -> None:
    assert invariant_6_violations(_PUSH_PR_LINE, _PUSH_PR_LINE) == []


def test_mcp_respelling_passes() -> None:
    assert invariant_6_violations("Read, mcp__serena__*", "Read, serena/*") == []


def test_list_form_passes() -> None:
    assert invariant_6_violations(["Bash(git:*)", "Read"], ["Bash(git:*)", "Read"]) == []


def test_missing_grant_on_both_sides_passes() -> None:
    assert invariant_6_violations(None, None) == []


# Predicate: negative controls ------------------------------------------------


def test_scoped_entry_degraded_to_bare_is_a_violation() -> None:
    problems = invariant_6_violations("Bash(git push:*), Read", "Bash, Read")
    assert problems == ["'Bash(git push:*)' widened to bare 'Bash'"]


def test_changed_argument_is_a_violation() -> None:
    problems = invariant_6_violations("Bash(git push:*)", "Bash(git:*)")
    assert problems == ["'Bash(git push:*)' argument changed to 'Bash(git:*)'"]


def test_dropped_entry_is_a_violation() -> None:
    assert invariant_6_violations("Bash(git add:*), Read", "Read") == ["entry count 2 became 1"]


def test_added_entry_is_a_violation() -> None:
    assert invariant_6_violations("Read", "Read, Bash") == ["entry count 1 became 2"]


def test_renamed_tool_is_a_violation() -> None:
    problems = invariant_6_violations("Bash(git add:*)", "Edit(git add:*)")
    assert problems == ["'Bash(git add:*)' renamed to 'Edit(git add:*)'"]


def test_commas_inside_parens_do_not_split() -> None:
    assert split_entries("Bash(a, b:*), Read") == ["Bash(a, b:*)", "Read"]


def test_unparseable_entry_raises() -> None:
    with pytest.raises(ValueError, match="unparseable"):
        parse_entry("")


# Generator transform ---------------------------------------------------------


def test_translate_allowed_tools_keeps_scoped_entries_verbatim() -> None:
    frontmatter = f"name: x\nallowed-tools: {_PUSH_PR_LINE}\ndescription: d\n"
    assert translate_allowed_tools(frontmatter) == frontmatter


def test_translate_skill_file_never_widens_a_scoped_grant() -> None:
    src = f"---\nname: x\nallowed-tools: {_PUSH_PR_LINE}\n---\nBody\n"
    projected = translate_skill_file(src, _OUT)
    line = next(ln for ln in projected.splitlines() if ln.startswith("allowed-tools:"))
    assert invariant_6_violations(_PUSH_PR_LINE, line.split(":", 1)[1].strip()) == []


# Shipped mirror --------------------------------------------------------------


def _is_scoped(skill: str) -> bool:
    entries = split_entries(_allowed_tools(SOURCE_SKILLS / skill / "SKILL.md"))
    return any(parse_entry(entry)[1] is not None for entry in entries)


def test_predicate_covers_the_argument_scoped_skills() -> None:
    scoped = [name for name in _skills_with_allowed_tools() if _is_scoped(name)]
    assert "push-pr" in scoped
    assert len(scoped) >= 16


@pytest.mark.parametrize("skill", _skills_with_allowed_tools())
def test_shipped_mirror_preserves_allowed_tools(skill: str) -> None:
    source = _allowed_tools(SOURCE_SKILLS / skill / "SKILL.md")
    projected = _allowed_tools(MIRROR_SKILLS / skill / "SKILL.md")
    assert projected is not None, f"{skill}: mirror dropped allowed-tools"
    assert invariant_6_violations(source, projected) == []
