"""Contract tests for the curating-memories SKILL.md (issue #5574).

The skill was written against the Forgetful MCP server: every operation it
documented (`update_memory`, `mark_memory_obsolete`, `link_memories`,
`query_memory`) was an `execute_forgetful_tool` call, and its "When to Use"
section routed the reader to `using-forgetful-memory` for the rest. That skill
was retired in #5575 and the server was decommissioned under #5574, so the
pointer resolved to nothing and every code block instructed a call that cannot
be made.

`.claude/skills/orphan-ref-validator/scripts/filters.py` carries
`using-forgetful-memory` in `KNOWN_RETIRED_KEBAB_SKILLS`, which suppresses the
bare-name mention, and `tests/skills/test_skill_md_cross_reference_links.py`
pins only `golden-principles` and `memory-enhancement`. Nothing gated the
relative Markdown link, which is why it survived two cleanup passes.

Parametrized over the canonical `.claude/` tree and the generated
`src/copilot-cli/` mirror so both copies satisfy the same contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

CANONICAL_SKILL_MD = REPO_ROOT / ".claude" / "skills" / "curating-memories" / "SKILL.md"
MIRROR_SKILL_MD = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "curating-memories" / "SKILL.md"
)

SKILL_MD_PATHS = [
    pytest.param(CANONICAL_SKILL_MD, id="canonical"),
    pytest.param(MIRROR_SKILL_MD, id="copilot-cli-mirror"),
]

_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]*)?\)")


@pytest.fixture(params=SKILL_MD_PATHS)
def skill_md_path(request: pytest.FixtureRequest) -> Path:
    path: Path = request.param
    return path


@pytest.fixture
def skill_content(skill_md_path: Path) -> str:
    assert skill_md_path.is_file(), f"SKILL.md not found at {skill_md_path}"
    return skill_md_path.read_text(encoding="utf-8")


def _names_forgetful(text: str) -> bool:
    """True when *text* names the decommissioned Forgetful server in any form.

    Case-folded because the removed surfaces spelled it three ways: `Forgetful`
    in the description and prose, `execute_forgetful_tool` in every code block,
    and `using-forgetful-memory` in the link and the bare-name mention.
    """
    return "forgetful" in text.lower()


def _unresolved_relative_links(source_file: Path, text: str) -> list[str]:
    """Relative Markdown link targets that do not resolve from *source_file*.

    Markdown resolves a relative link against the directory of the file that
    contains it, never against the repo root, so this mirrors that rule. Absolute
    URLs are skipped; they are not this test's concern.
    """
    unresolved: list[str] = []
    for target in _MD_LINK_RE.findall(text):
        if "://" in target or target.startswith("mailto:"):
            continue
        if not (source_file.parent / target).resolve().exists():
            unresolved.append(target)
    return unresolved


def test_skill_names_no_decommissioned_forgetful_surface(skill_content: str) -> None:
    """The skill documents no operation against the retired server."""
    assert not _names_forgetful(skill_content)


def test_the_forgetful_detector_catches_every_spelling_it_guards() -> None:
    """Negative control: the guard above is not vacuous.

    Fires on each of the three spellings the rewrite removed and stays quiet on
    the Serena wording that replaced them.
    """
    assert _names_forgetful("description: Guidance for maintaining Forgetful record quality")
    assert _names_forgetful('execute_forgetful_tool("mark_memory_obsolete", {')
    assert _names_forgetful("Use [using-forgetful-memory](../using-forgetful-memory/SKILL.md)")

    assert not _names_forgetful("Maintain Serena memory files in place.")
    assert not _names_forgetful("Use `memory-consolidate` for cross-file merges.")
    assert not _names_forgetful("")


def test_every_relative_link_resolves(skill_md_path: Path, skill_content: str) -> None:
    """No Markdown link points at a path that does not exist in this tree.

    The retired-skill link is the case this closes, but the check is general:
    the mirror nests skills at a different depth from the source, so a link that
    resolves in one tree can still be dead in the other.
    """
    assert _unresolved_relative_links(skill_md_path, skill_content) == []


def test_the_link_resolver_catches_a_dead_target() -> None:
    """Negative control: the resolver flags the exact link that was dead here.

    Uses the real SKILL.md location so the relative depth is the one the
    renderer would apply, and pairs the dead target with a live sibling so a
    resolver that flagged everything would fail this too.
    """
    dead = "[using-forgetful-memory](../using-forgetful-memory/SKILL.md)"
    live = "[doc-accuracy](../doc-accuracy/SKILL.md)"

    found = _unresolved_relative_links(CANONICAL_SKILL_MD, f"{dead}\n{live}\n")

    assert found == ["../using-forgetful-memory/SKILL.md"]


def test_skill_does_not_claim_ownership_of_memory_consolidate_work(
    skill_content: str,
) -> None:
    """The scope split with `memory-consolidate` survives the rewrite.

    `memory-consolidate` owns cross-file merges, deletions, and index cleanup.
    Losing that hand-off would let two skills edit the same files with
    different rules.
    """
    assert "memory-consolidate" in skill_content
    assert "never edits Serena index files" in skill_content
