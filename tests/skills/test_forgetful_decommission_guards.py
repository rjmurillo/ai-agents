"""Guard tests for the skills cleaned of Forgetful surfaces in issue #5574.

PR #5616 removed the Forgetful references it had enumerated in a fixed file
list. Scoping by file list rather than by call site left 59 live
`execute_forgetful_tool` call sites in skill bodies, plus three dead links to
`using-forgetful-memory` (retired in #5575) and several statements about the
repository that stopped being true when Stage 1 removed the server from
`.mcp.json`.

This module guards the surfaces cleaned in the follow-up. It does not cover
`encode-repo-serena`, `research-and-incorporate`, or `serena-code-architecture`:
those three are Forgetful-native rather than Forgetful-flavored, so whether they
are retired or rewritten is an owner decision, and they still name the server on
purpose until it is made.

Each guard is parametrized over the canonical `.claude/` tree and the generated
`src/copilot-cli/` mirror so a regeneration cannot reintroduce a surface on one
side only. `test_guard_detects_every_removed_spelling` is the negative control:
without it, a guard that silently stopped matching would pass on every file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_ROOT = REPO_ROOT / ".claude" / "skills"
MIRROR_ROOT = REPO_ROOT / "src" / "copilot-cli" / "skills"

# Relative to a skills root. Every entry had at least one Forgetful surface
# removed; see the PR body for what each one was.
CLEANED_SKILL_FILES = (
    "ai-agents-build-and-env/SKILL.md",
    "memory-consolidate/SKILL.md",
    "memory-documentary/SKILL.md",
    "memory-documentary/references/execution-protocol.md",
    "reflect/SKILL.md",
    "reflect/references/integration-and-design.md",
    "threat-modeling/SKILL.md",
    "using-serena-symbols/SKILL.md",
)

TREE_ROOTS = (
    pytest.param(CANONICAL_ROOT, id="canonical"),
    pytest.param(MIRROR_ROOT, id="copilot-cli-mirror"),
)

# The five spellings this cleanup removed. Case-folded matching collapses
# `Forgetful` and `forgetful`; the rest are distinct tokens that a partial
# revert could reintroduce one at a time.
REMOVED_SPELLINGS = (
    "Forgetful",
    "forgetful",
    "execute_forgetful_tool",
    "mcp__forgetful__",
    "using-forgetful-memory",
)


def _names_forgetful(text: str) -> bool:
    """True when *text* names the decommissioned Forgetful server in any form.

    Case-folded because the removed surfaces spelled it several ways: capitalized
    in prose and skill descriptions, lowercase in the `.mcp.json` server table,
    and as the `execute_forgetful_tool` / `using-forgetful-memory` identifiers.
    """
    return "forgetful" in text.casefold()


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file not found: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("skills_root", TREE_ROOTS)
@pytest.mark.parametrize("relative_path", CLEANED_SKILL_FILES)
def test_cleaned_skill_names_no_forgetful_surface(
    skills_root: Path, relative_path: str
) -> None:
    """Positive guard: no cleaned skill file names the retired server."""
    path = skills_root / relative_path
    content = _read(path)
    assert not _names_forgetful(content), (
        f"{path} reintroduced a Forgetful surface; the server was "
        "decommissioned under #5574 and no harness can grant it"
    )


@pytest.mark.parametrize("spelling", REMOVED_SPELLINGS)
def test_guard_detects_every_removed_spelling(spelling: str) -> None:
    """Negative control: the guard is not vacuous.

    Each string below is a spelling actually removed by this change. If
    `_names_forgetful` stopped matching one, the positive guard above would pass
    on a file that still carried it.
    """
    assert _names_forgetful(f"prefix {spelling} suffix"), (
        f"guard no longer detects {spelling!r}; the positive tests above are "
        "passing vacuously"
    )


def test_guard_does_not_fire_on_unrelated_memory_prose() -> None:
    """Edge: the guard keys on the server name, not on memory vocabulary.

    Every cleaned file still discusses Serena memory at length. A guard that
    matched "memory" would fail all eight files for the wrong reason.
    """
    assert not _names_forgetful(
        "Store the summary as a Serena memory with mcp__serena__write_memory."
    )


@pytest.mark.parametrize("skills_root", TREE_ROOTS)
def test_using_serena_symbols_routes_memory_guidance_to_a_live_skill(
    skills_root: Path,
) -> None:
    """The `Do NOT use` clause pointed at `using-forgetful-memory`, deleted in #5575.

    A routing description is what the harness reads to pick a skill, so a dead
    name there sends the reader nowhere.
    """
    content = _read(skills_root / "using-serena-symbols" / "SKILL.md")
    assert "for memory guidance (use memory)" in content


@pytest.mark.parametrize("skills_root", TREE_ROOTS)
@pytest.mark.parametrize(
    "relative_path",
    ("reflect/SKILL.md", "reflect/references/integration-and-design.md"),
)
def test_reflect_related_table_drops_the_deleted_skill_row(
    skills_root: Path, relative_path: str
) -> None:
    """Both copies of the Related table carried a row for a skill that is gone."""
    content = _read(skills_root / relative_path)
    assert "| `curating-memories` |" in content, (
        "the surviving rows must stay; this test would pass vacuously if the "
        "whole table were deleted"
    )


@pytest.mark.parametrize("skills_root", TREE_ROOTS)
def test_memory_consolidate_boundary_names_the_live_sibling_contract(
    skills_root: Path,
) -> None:
    """`curating-memories` curates Serena files in place after #5616, not a store.

    The old clause routed "Forgetful-store curation" to a skill that no longer
    does that, so the boundary named a store instead of an operation.
    """
    content = _read(skills_root / "memory-consolidate" / "SKILL.md")
    assert "in-file supersession markers (use curating-memories)" in content


@pytest.mark.parametrize("skills_root", TREE_ROOTS)
def test_memory_documentary_counts_three_memory_systems(skills_root: Path) -> None:
    """The count words carry no `forgetful` substring, so the guard cannot see them.

    Dropping the Forgetful tier without fixing "all 4 memory systems" would leave
    the description promising a source the protocol no longer queries.
    """
    content = _read(skills_root / "memory-documentary" / "SKILL.md")
    assert "all 3\n  memory systems (Claude-Mem, Serena, DeepWiki)" in content
    assert "the three memory systems as evidence inputs" in content
    assert "Check all 3 MCP servers" in content


def test_build_and_env_server_table_matches_mcp_json() -> None:
    """Pin the doc to the file it tells the reader to `cat`.

    Stage 1 removed forgetful from `.mcp.json` but the runbook kept claiming
    three servers and kept forgetful in its table, so the documented setup and
    the real one disagreed. Asserting against `.mcp.json` itself means the next
    server added or removed fails this test instead of drifting silently.
    """
    servers = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    configured = sorted(servers["mcpServers"])
    assert configured == ["deepwiki", "serena"], (
        f".mcp.json now defines {configured}; update the "
        "ai-agents-build-and-env server table and this test together"
    )

    content = _read(CANONICAL_ROOT / "ai-agents-build-and-env" / "SKILL.md")
    assert "`.mcp.json` at repo root defines two servers." in content
    assert "| MCP servers serena/deepwiki | `.mcp.json` | `cat .mcp.json` |" in content
    for name in configured:
        assert f"| {name} |" in content, (
            f"{name} is configured in .mcp.json but absent from the server table"
        )
