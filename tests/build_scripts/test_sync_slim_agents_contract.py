"""Frontmatter contract and shipped-constant tests for build/sync_slim_agents.py.

Split out of `test_sync_slim_agents.py`, which crossed the 500-line taste
limit. The seam is the fixture: nothing here builds a temporary tree. These
cases exercise the delimiter parsing as pure functions and read the shipped
module constants directly, which is the only way to see an inverted sync
direction, because the tree fixture in the sibling module monkeypatches the
constants the direction lives in.

Tests:
- Edge: split_frontmatter handles absent, unterminated, empty, and
  end-of-file delimiters.
- Edge: an opener is a line that is exactly `---`, with or without a
  trailing newline; `---abc` is not one.
- Platform: reported paths use forward slashes, proved with PureWindowsPath
  so the assertion is not vacuous on a POSIX host.
- Contract: the shipped source is `src/claude/`, and `.claude/agents/` is in
  no destination.
- Contract: the shipped agent list resolves in every tree, with no unsafe or
  malformed file.
- Contract: the shipped destinations strip `mcp__github__` and not
  `mcp__serena__`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path, PureWindowsPath

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "build" / "sync_slim_agents.py"

# A distinct module name, so loading here cannot displace the sibling module's
# own instance in sys.modules and silently share monkeypatched constants.
_spec = importlib.util.spec_from_file_location("sync_slim_agents_contract", _SCRIPT)
assert _spec is not None and _spec.loader is not None
sync_slim_agents = importlib.util.module_from_spec(_spec)
sys.modules["sync_slim_agents_contract"] = sync_slim_agents
_spec.loader.exec_module(sync_slim_agents)


# The nine mirrored slim targets, from AC-7 in
# .agents/archive/planning/SPEC-agent-consolidation.md: "9 of the 11 slim
# targets (explainer, implementer, issue-feature-review, roadmap,
# milestone-planner, analyst, critic, orchestrator, skillbook) are propagated
# to all four mirror locations". Held here rather than derived from the module,
# so a deletion from SLIMMED_AGENTS fails instead of quietly shrinking the set
# of files the tool checks.
_SPEC_SLIM_TARGETS = frozenset(
    {
        "analyst",
        "critic",
        "explainer",
        "implementer",
        "issue-feature-review",
        "milestone-planner",
        "orchestrator",
        "roadmap",
        "skillbook",
    }
)

AGENT = "analyst"
SOURCE_BODY = "# Analyst\n\nBody from the Claude tree.\n"
CLAUDE_FRONTMATTER = "---\nname: analyst\nmodel: sonnet\n---\n"
UNTERMINATED_FRONTMATTER = "---\nname: analyst\nstill open\n\n# Body\n"


def test_relative_paths_use_forward_slashes_on_windows(monkeypatch) -> None:
    """A POSIX-only assertion cannot see this: str() and as_posix() agree there.

    PureWindowsPath does the path arithmetic Windows would do, on any host, so
    reverting the cast to str() fails here instead of passing everywhere.
    """
    root = PureWindowsPath("C:/repo")
    monkeypatch.setattr(sync_slim_agents, "REPO_ROOT", root)

    reported = sync_slim_agents._relative(
        root / "templates" / "agents" / f"{AGENT}.shared.md"
    )

    assert reported == "templates/agents/analyst.shared.md"


def test_split_frontmatter_returns_whole_text_when_absent() -> None:
    assert sync_slim_agents.split_frontmatter("no frontmatter\n") == (
        "",
        "no frontmatter\n",
    )


def test_split_frontmatter_returns_whole_text_when_unterminated() -> None:
    text = "---\nname: analyst\nstill open\n"
    assert sync_slim_agents.split_frontmatter(text) == ("", text)


def test_split_frontmatter_keeps_both_delimiters_in_the_frontmatter() -> None:
    frontmatter, body = sync_slim_agents.split_frontmatter(
        CLAUDE_FRONTMATTER + SOURCE_BODY
    )
    assert frontmatter == CLAUDE_FRONTMATTER
    assert body == SOURCE_BODY


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nname: analyst\nstill open\n", True),
        (UNTERMINATED_FRONTMATTER, True),
        (CLAUDE_FRONTMATTER + SOURCE_BODY, False),
        ("no frontmatter\n", False),
        ("", False),
        ("---\n", True),
        ("---", True),
        ("---abc\n", False),
        ("---\n---\n" + SOURCE_BODY, False),
        ("---\nname: analyst\n---", False),
        ("---\n---", False),
    ],
)
def test_has_unterminated_frontmatter(text: str, expected: bool) -> None:
    assert sync_slim_agents.has_unterminated_frontmatter(text) is expected


def test_split_frontmatter_accepts_an_empty_block() -> None:
    """`---` on one line and `---` on the next is empty frontmatter, not broken."""
    assert sync_slim_agents.split_frontmatter("---\n---\n" + SOURCE_BODY) == (
        "---\n---\n",
        SOURCE_BODY,
    )


def test_split_frontmatter_accepts_a_closer_at_end_of_file() -> None:
    """A closing `---` with no trailing newline still closes the block."""
    text = "---\nname: analyst\n---"
    assert sync_slim_agents.split_frontmatter(text) == (text, "")


def test_shipped_source_is_the_canonical_claude_tree() -> None:
    """`src/claude/` is the edit-here source; `.claude/agents/` is the runtime copy.

    The tree fixture in the sibling module monkeypatches AGENT_SOURCE and
    DESTINATIONS, so no test that uses it can see an inverted shipped
    direction. This one reads the shipped constants directly, which is the
    only place the inversion shows.

    The destination set is pinned exactly, not merely checked for the two
    directories that must stay out. Excluding the wrong entries would still
    pass with a mirror deleted, which is how the draft this PR replaces left
    `.github/agents/` silently stale.
    """
    assert sync_slim_agents.AGENT_SOURCE == _REPO_ROOT / "src" / "claude"
    assert {
        (destination.directory, destination.suffix)
        for destination in sync_slim_agents.DESTINATIONS
    } == {
        (_REPO_ROOT / "templates" / "agents", ".shared.md"),
        (_REPO_ROOT / ".github" / "agents", ".agent.md"),
    }


def test_shipped_slimmed_agents_match_the_spec() -> None:
    """The declared list is exactly AC-7's nine, checked before path existence.

    `find_missing_paths` returns an empty list for an empty input, so an
    existence check alone passes just as happily with entries deleted as with
    the full set. Pinning the tuple is what makes a deletion fail.
    """
    assert set(sync_slim_agents.SLIMMED_AGENTS) == _SPEC_SLIM_TARGETS
    assert len(sync_slim_agents.SLIMMED_AGENTS) == len(_SPEC_SLIM_TARGETS)


def test_shipped_slimmed_agents_all_exist_in_every_tree() -> None:
    """The real declared list must not name an agent that no tree has.

    An earlier draft carried `spec-generator`, which is a skill, not an agent.
    """
    assert sync_slim_agents.find_missing_paths(sync_slim_agents.SLIMMED_AGENTS) == []


def test_shipped_trees_carry_no_unsafe_or_malformed_paths() -> None:
    """The live tree passes the two guards, so the gate is not shipping red."""
    assert sync_slim_agents.find_unsafe_paths(sync_slim_agents.SLIMMED_AGENTS) == []
    assert sync_slim_agents.find_malformed_paths(sync_slim_agents.SLIMMED_AGENTS) == []


def test_shipped_destinations_strip_github_and_leave_serena() -> None:
    """Reads the shipped constants: the tree fixture monkeypatches them away.

    Pins the rule against its evidence. `mcp__github__` is in `src/claude/` 26
    times and in neither mirror; `mcp__serena__` is in all three trees, so a
    transform that stripped it would rewrite mirror lines that are correct.

    Goes through the text layer instance the CLI module itself loaded, rather
    than loading a second one here. Two instances would define two `Transform`
    classes, and a dataclass `__eq__` returns NotImplemented across classes, so
    the first assertion below would compare the shipped rule set against a
    structurally identical stranger and fail.
    """
    reconcile = sync_slim_agents._reconcile

    for destination in sync_slim_agents.DESTINATIONS:
        assert destination.transforms == reconcile.MIRROR_TRANSFORMS

    rewritten = reconcile.transformed_body(
        "mcp__github__issue_read and mcp__serena__read_memory\n",
        reconcile.MIRROR_TRANSFORMS,
    )

    assert rewritten == "issue_read and mcp__serena__read_memory\n"
