"""Guard tests for the skills cleaned of Forgetful surfaces in issue #5574.

PR #5616 removed the Forgetful references it had enumerated in a fixed file
list. Scoping by file list rather than by call site left 59 live
`execute_forgetful_tool` call sites in skill bodies, plus three dead links to
`using-forgetful-memory` (retired in #5575) and several statements about the
repository that stopped being true when Stage 1 removed the server from
`.mcp.json`.

This module guards the surfaces cleaned in the follow-up. It does not cover the
three Forgetful-native skills, whose call sites were not fixable in place: the
owner retired them under #5624, so their surfaces are gone rather than guarded.

A second wave added eight more entries: the last skill files in the acceptance
criterion's scope that still named the server. They were live instructions
(`programming-advisor`, `world-model-diagnostic`), a stale claim citing an ADR
that ADR-106 superseded (`ai-agents-docs-of-record`), an invocation example
(`slashcommandcreator`), and prose treating the server as a second live backend
(`software-engineering-library` references, `memory/references`).

Each guard is parametrized over the canonical `.claude/` tree and the generated
`src/copilot-cli/` mirror so a regeneration cannot reintroduce a surface on one
side only. `test_guard_detects_every_removed_spelling` is the negative control:
without it, a guard that silently stopped matching would pass on every file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

CANONICAL_ROOT = REPO_ROOT / ".claude" / "skills"
MIRROR_ROOT = REPO_ROOT / "src" / "copilot-cli" / "skills"

# Relative to a skills root. Every entry had at least one Forgetful surface
# removed; see the PR body for what each one was.
CLEANED_SKILL_FILES = (
    "ai-agents-build-and-env/SKILL.md",
    "ai-agents-docs-of-record/SKILL.md",
    "memory-consolidate/SKILL.md",
    "memory-documentary/SKILL.md",
    "memory-documentary/references/execution-protocol.md",
    "memory/references/zettelkasten-memory-agents.md",
    "programming-advisor/SKILL.md",
    "reflect/SKILL.md",
    "reflect/references/integration-and-design.md",
    "slashcommandcreator/SKILL.md",
    "software-engineering-library/references/domain-driven-design.md",
    "software-engineering-library/references/enterprise-patterns.md",
    "software-engineering-library/references/release-it.md",
    "threat-modeling/SKILL.md",
    "using-serena-symbols/SKILL.md",
    "world-model-diagnostic/SKILL.md",
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

# memory-documentary went from four memory systems to three. The count words carry
# no `forgetful` substring, so the guard above cannot see them and they need their
# own scan.
MEMORY_DOCUMENTARY_FILES = (
    "memory-documentary/SKILL.md",
    "memory-documentary/references/execution-protocol.md",
)

_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
}

# Any count immediately qualifying "MCP server(s)" or "memory system(s)". `\s+`
# rather than a literal space because the YAML frontmatter description wraps the
# count onto the line above its noun.
#
# "data sources" is deliberately NOT matched. Those include the .agents/ artifact
# trees and GitHub issues alongside the memory systems, so "4+ data sources" in
# the execution protocol is correct and was never part of the tier removal.
_MEMORY_COUNT_RE = re.compile(
    r"\b(?P<count>\d+|one|two|three|four|five|six)\s+(?:MCP servers?|memory systems?)\b",
    re.IGNORECASE,
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
@pytest.mark.parametrize("relative_path", MEMORY_DOCUMENTARY_FILES)
def test_every_memory_system_count_says_three(
    skills_root: Path, relative_path: str
) -> None:
    """Every count qualifying "MCP server" or "memory system" must read three.

    The first version of this guard pinned three hand-picked strings, so it proved
    the edits that were made and nothing about the ones that were missed. Devin
    Review found two it could not see: the Process heading still read
    "Memory Systems (4 MCP servers)" five lines above its own three-item list, and
    the Verification checklist still required all four to have been queried, which
    no complete three-source report could satisfy.

    Scanning for the pattern instead of for known strings means a count-bearing
    surface added later is covered without editing this test.
    """
    content = _read(skills_root / relative_path)
    wrong = [
        match.group(0)
        for match in _MEMORY_COUNT_RE.finditer(content)
        if _COUNT_WORDS[match.group("count").lower()] != 3
    ]
    assert not wrong, (
        f"{relative_path} states a memory-system count that is not three: {wrong}"
    )


def test_memory_system_count_scan_is_not_vacuous() -> None:
    """Negative control: the scan above passes because counts are right, not absent.

    Without this, deleting every count-bearing sentence would turn the guard green.
    """
    content = _read(CANONICAL_ROOT / "memory-documentary" / "SKILL.md")
    matches = list(_MEMORY_COUNT_RE.finditer(content))
    assert len(matches) >= 3, (
        f"expected at least 3 count-bearing phrases in the skill, found {len(matches)}; "
        "if the wording changed, update the pattern rather than deleting this guard"
    )

    # The pattern must actually catch a wrong count, including across the line
    # wrap that YAML frontmatter puts in the description.
    for probe in ("Memory Systems (4 MCP servers)", "all 4\n  memory systems"):
        found = _MEMORY_COUNT_RE.search(probe)
        assert found is not None, f"pattern no longer matches {probe!r}"
        assert _COUNT_WORDS[found.group("count").lower()] == 4


@pytest.mark.parametrize("skills_root", TREE_ROOTS)
def test_memory_systems_heading_count_matches_the_list_beneath_it(
    skills_root: Path,
) -> None:
    """Structural check: the declared server count equals the servers listed.

    This is the check that would have caught the miss directly. The heading and
    the list it introduces sat five lines apart and disagreed by one, because the
    Forgetful bullet was deleted from the list and the heading was not updated.
    """
    content = _read(skills_root / "memory-documentary" / "SKILL.md")
    block = re.search(
        r"\*\*Memory Systems \((?P<count>\d+) MCP servers\)\*\*:\n\n(?P<items>(?:- .*\n)+)",
        content,
    )
    assert block is not None, (
        "the Memory Systems block changed shape; update this guard alongside it "
        "rather than letting it pass vacuously"
    )
    declared = int(block.group("count"))
    listed = sum(
        1 for line in block.group("items").splitlines() if line.startswith("- ")
    )
    assert declared == listed, (
        f"heading declares {declared} MCP servers but {listed} are listed beneath it"
    )


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
