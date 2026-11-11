"""The /review fallback for a host with no subagent tool (issue #7226, step 4).

The earlier fallback ran every axis as a ``claude -p`` process and recorded
``UNKNOWN`` for every axis when ``claude`` was not on ``PATH``. On Codex and
Muse Code that is every run, so ``/review`` gave no verdict there. The
contract now is three ordered paths: the host's own subagent tool, then
``claude -p``, then each axis in this session, which never writes the marker.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RESOURCE = Path("skills/review/resources/marker-and-no-task.md")
SKILL = Path("skills/review/SKILL.md")
TREES = ("src/claude", "src/codex", "src/muse", "src/copilot-cli", "src/cursor")
SECTION = "## Running without a subagent tool"


def _section(text: str, heading: str = SECTION) -> str:
    start = text.index(heading)
    following = text.find("\n## ", start + len(heading))
    return text[start:] if following == -1 else text[start:following]


def _paths(section: str) -> list[str]:
    """Split the numbered top-level paths (``1. **...**``) out of the section."""
    parts = re.split(r"(?m)^(?=\d\. \*\*)", section)
    return [p for p in parts[1:] if p.strip()]


def _resource(tree: str = "src/claude") -> str:
    return (REPO_ROOT / tree / RESOURCE).read_text(encoding="utf-8")


def test_resource_offers_three_paths_in_order() -> None:
    paths = _paths(_section(_resource()))

    assert len(paths) == 3
    assert "subagent tool" in paths[0]
    assert "claude -p" in paths[1]
    assert "in this session" in paths[2]


def test_first_path_names_every_host_spawn_tool() -> None:
    first = _paths(_section(_resource()))[0]

    for tool in ("`Task`", "`task`", "`spawn_agent`", "`subagent_spawn`"):
        assert tool in first, tool


def test_codex_child_gets_no_parent_context() -> None:
    first = _paths(_section(_resource()))[0]

    assert "`fork_turns` set to `none`" in first


def test_in_session_path_never_writes_the_marker() -> None:
    third = _paths(_section(_resource()))[2]

    assert "NEVER writes the PASS marker" in third
    assert "in-session review, no marker" in third


def test_missing_claude_no_longer_forces_unknown_for_every_axis() -> None:
    section = _section(_resource())

    assert "If `claude` is not on `PATH`, record `UNKNOWN` for every axis" not in section


def test_scope_check_still_applies_to_cli_and_in_session_paths() -> None:
    section = _section(_resource())

    assert "On paths 2 and 3, run `validate_findings_scope.py`" in section


@pytest.mark.parametrize("tree", TREES)
def test_every_shipped_tree_carries_the_same_fallback(tree: str) -> None:
    assert _section(_resource(tree)) == _section(_resource())


@pytest.mark.parametrize("tree", TREES)
def test_skill_points_at_the_resource_and_forbids_in_session_markers(tree: str) -> None:
    skill = (REPO_ROOT / tree / SKILL).read_text(encoding="utf-8")
    section = _section(skill)

    assert "resources/marker-and-no-task.md" in section
    assert "never writes the marker" in section
    assert "## Running without the Task tool" not in skill


def test_section_parser_rejects_a_dropped_path() -> None:
    section = _section(_resource())
    without_third = section[: section.index("3. **")]

    assert len(_paths(without_third)) == 2
