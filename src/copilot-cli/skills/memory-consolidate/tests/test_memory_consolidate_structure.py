"""Structural tests for the memory-consolidate sub-skill (ADR-063).

Pins the sub-skill's core contract only: frontmatter identity (no stale
rename), the three named phases, the durable/dated split, duplicate-only
merge, date anchoring (or `AMBIGUOUS-DATE`), index budgets, the ADR-056
output envelope, no self-authorized physical deletion, Serena's
indexes-only discovery scope, mirror-safe `REPO_ROOT` resolution, and
canonical-script separation from discovery, plus router registration in
`memory`'s SKILL.md. This module is mirrored into
`src/copilot-cli/skills/memory-consolidate/tests/` at a different tree
depth, so `REPO_ROOT` anchors on `pyproject.toml`, never a fixed
`parents[N]` index.
"""

from __future__ import annotations

import re
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk up to the ancestor holding pyproject.toml (mirror-safe anchor)."""
    return next(p for p in start.parents if (p / "pyproject.toml").is_file())


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
REPO_ROOT = _find_repo_root(SKILL_DIR)
MEMORY_README = REPO_ROOT / ".serena" / "memories" / "README.md"
MEMORY_ROUTER_MD = REPO_ROOT / ".claude" / "skills" / "memory" / "SKILL.md"

_FRONTMATTER = re.compile(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n")
_BACKTICK_TRIGGER = re.compile(r"`[^`]+`")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _unwrapped(text: str) -> str:
    """Collapse markdown soft line-wraps so phrase checks survive rewraps."""
    return " ".join(text.split())


def _frontmatter_block() -> str:
    match = _FRONTMATTER.search(_read(SKILL_MD))
    assert match is not None, "SKILL.md must open with a --- frontmatter block"
    return match.group(1)


def test_frontmatter_identity_and_size_ceiling() -> None:
    # Arrange
    block = _frontmatter_block()
    body = _read(SKILL_MD)

    # Act / Assert: exact, current identifier; no stale rename survives.
    assert SKILL_DIR.name == "memory-consolidate"
    assert re.search(r"^name:\s*memory-consolidate\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly memory-consolidate, not a stale variant"
    )
    assert len(body.splitlines()) <= 500, "SKILL.md exceeds the 500-line ceiling"
    triggers = _BACKTICK_TRIGGER.findall(block)
    assert 3 <= len(triggers) <= 5, f"expected 3-5 trigger phrases, found {len(triggers)}"


def test_description_names_durable_and_dated_split() -> None:
    block = _frontmatter_block().lower()
    assert "durable" in block, "description must name the durable-context concept"
    assert "dated" in block, "description must name the dated-context concept"


def test_process_has_three_named_phases() -> None:
    body = _read(SKILL_MD)
    assert re.search(r"^### Phase 1: Take Stock", body, re.MULTILINE)
    assert re.search(r"^### Phase 2: Consolidate", body, re.MULTILINE)
    assert re.search(r"^### Phase 3: Tidy the Index", body, re.MULTILINE)


def test_merge_boundary_bounded_to_genuine_duplicates() -> None:
    body = _unwrapped(_read(SKILL_MD)).lower()
    assert "genuine duplicate" in body, "must bound merging to genuine duplicates"
    assert "distinct atomic concepts" in body, "must forbid merging distinct concepts"


def test_date_anchor_is_source_stamp_not_session_clock() -> None:
    body = _unwrapped(_read(SKILL_MD)).lower()
    assert "source stamp" in body or "[yyyy-mm-dd]" in body, (
        "must anchor date resolution on the observation's source stamp"
    )
    assert "file history" in body, "must offer file history as fallback anchor"
    assert "ambiguous-date" in body, "must flag an unanchored date, not guess it"
    assert "against the current session date" not in body, (
        "must not anchor dates on the session's wall-clock date"
    )


def test_index_budget_is_own_operational_target() -> None:
    body = _read(SKILL_MD)
    assert "200 lines" in body, "must state the 200-line index budget"
    assert "25 KB" in body or "25,600" in body, "must state the 25 KB index budget"
    assert "own operational budget" in body.lower(), (
        "budget must be framed as this skill's own target, not README.md's"
    )


def test_output_envelope_present_exactly_once() -> None:
    body = _read(SKILL_MD)
    assert body.count("## Output") == 1, "must have exactly one ## Output section"
    for field in ("Success", "Data", "Error", "Metadata"):
        assert f"**{field}**" in body, f"Output section must name the {field} field"
    assert re.search(r"^\s*adr:.*ADR-056", _frontmatter_block(), re.MULTILINE), (
        "frontmatter metadata.adr must declare ADR-056"
    )


def test_never_physically_deletes_without_ratification() -> None:
    body = _unwrapped(_read(SKILL_MD)).lower()
    assert "never physically deletes" in body, "must state it never deletes"
    assert "ratification" in body, "must require a ratification step"
    assert "human-confirmed" in body, "must name a human-confirmed gate"
    assert "dangling" in body, "must prohibit dangling supersedes references"
    assert "still exists" in body or "still on disk" in body, (
        "a superseded file must stay on disk, not be deleted by this skill"
    )


def test_serena_scope_is_indexes_only_and_repo_root_is_mirror_safe() -> None:
    # Arrange: README.md draws the top-level-vs-subdirectory line this
    # skill's Phase 1 must restate correctly, in both tree copies.
    assert MEMORY_README.is_file(), f"missing canonical README at {MEMORY_README}"
    readme = _read(MEMORY_README)
    body = _read(SKILL_MD)
    assert "visible in `list_memories`" in readme
    assert "hidden from `list_memories`" in readme

    # Act / Assert: SKILL.md matches the indexes-only contract.
    assert "top-level files only" in body or "top-level only" in body
    assert "hidden from" in body
    assert "*-index.md" in body, "must direct readers to topic index files"

    # Act / Assert: REPO_ROOT resolves to the true root regardless of tree
    # depth (canonical .claude/... or mirrored src/copilot-cli/...), so a
    # fixed parents[N] index cannot silently regress this.
    resolved = _find_repo_root(SKILL_DIR)
    assert (resolved / "pyproject.toml").is_file()
    assert (resolved / ".serena" / "memories" / "README.md").is_file()


def test_canonical_checks_run_separately_from_discovery() -> None:
    body = _unwrapped(_read(SKILL_MD))
    for script in (
        "supersession_sweep.py",
        "count_memory_tokens.py",
        "test_memory_size.py",
    ):
        assert script in body, f"Phase 1 must retain canonical check {script}"
    assert "These three tiers govern discovery only" in body
    assert "run them regardless of which tier surfaced that list" in body


def test_memory_router_registers_consolidate_sub_skill() -> None:
    assert MEMORY_ROUTER_MD.is_file(), f"missing memory router at {MEMORY_ROUTER_MD}"
    assert "memory-consolidate" in _read(MEMORY_ROUTER_MD), (
        "memory's router SKILL.md must register memory-consolidate as an operation sibling"
    )
