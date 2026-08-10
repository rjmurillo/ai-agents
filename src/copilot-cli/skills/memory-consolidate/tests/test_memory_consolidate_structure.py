"""Structural tests for the memory-consolidate sub-skill.

ADR-063 (accepted 2026-06-17) decomposes the memory router by operation. This
phase adds a fifth operation sibling: a periodic, prompt-driven consolidation
pass over Serena memory files (durable-versus-dated separation, overlap
merging, relative-to-absolute date conversion, and index tidying) while
`memory` remains the thin router. These tests pin the contract the sub-skill
must honor:

- SKILL.md exists with required frontmatter (name, description) and stays
  under the 500-line ceiling (`.claude/skills/CLAUDE.md`).
- The description names the durable/dated split and carries 3 to 5
  backtick-wrapped trigger phrases (SkillForge requirement).
- The skill points callers at the canonical supersession sweep and size
  scripts rather than reimplementing them, and does not duplicate the Size
  Constraints table or the sweep's four bucket names verbatim; it links to
  `.serena/memories/README.md` and `curating-memories/SKILL.md` instead.
- The Process section documents exactly the three phases the skill commits
  to (Take Stock, Consolidate, Tidy the Index).
- `REPO_ROOT` is located by walking up to the ancestor holding
  `pyproject.toml`, not by a fixed `parents[N]` index, because this module
  is mirrored into `src/copilot-cli/skills/memory-consolidate/tests/` at a
  different depth than the canonical copy.
- `mcp__serena__list_memories` enumerates top-level index files only, per
  `.serena/memories/README.md`'s "Directory Structure" contract; the reader
  must be directed to topic `*-index.md` files for atomic memory paths.
- Discovery order (memory skills, then Serena MCP, then direct files) is
  separate from the always-run canonical scripts (sweep, token count, size
  check), which run regardless of which tier surfaced the file list.
- This skill never claims authority to physically delete a memory file, and
  never frames a ratification check as an anti-pattern to route around.
  Merging or retiring a file uses the healthy-supersession pattern in
  place; physical removal is a proposal for separate, human-confirmed
  ratification, never a self-performed action. A `supersedes` relation
  must never point at a file this skill deleted.
- Relative dates are resolved against the observation's own `[YYYY-MM-DD]`
  source stamp or recoverable file history, never the session's wall-clock
  date; an unanchored relative date is flagged, not guessed.
- Merging is bounded to genuine duplicates about the same entity (person,
  project, or preference); distinct atomic concepts stay separate even
  when topically adjacent.

Tests follow Arrange/Act/Assert, one behavior per test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    """Locate the repo root by walking up to the ancestor with pyproject.toml.

    This module is mirrored into `src/copilot-cli/skills/memory-consolidate/
    tests/`, so a fixed `parents[N]` index resolves correctly in only one tree
    (it under-counts in the mirror, landing on `src/` instead of the repo
    root) and silently mis-locates `.serena/memories/README.md` in the other.
    `pyproject.toml` lives only at the true repo root in both trees, so
    anchoring on it is reliable regardless of which copy runs the test.
    """
    return next(p for p in start.parents if (p / "pyproject.toml").is_file())


SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
REPO_ROOT = _find_repo_root(SKILL_DIR)
MEMORY_README = REPO_ROOT / ".serena" / "memories" / "README.md"

_FRONTMATTER = re.compile(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n")
_BACKTICK_TRIGGER = re.compile(r"`[^`]+`")
_SIZE_TABLE_ROW = re.compile(
    r"^>?\s*\|\s*Characters\s*\|\s*([\d,]+ max)\s*\|.*?\n"
    r"^>?\s*\|\s*Skills \(H2 sections\)\s*\|\s*(\d+ max)\s*\|.*?\n"
    r"^>?\s*\|\s*Categories \(H1 sections\)\s*\|\s*(\d+ max)\s*\|",
    re.MULTILINE,
)


def _read_skill() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _read_skill_unwrapped() -> str:
    """SKILL.md text with markdown soft line-wraps collapsed to spaces.

    Prose sometimes wraps across a line break that is a rendering artifact,
    not a paragraph boundary (for example "this skill never\nphysically
    deletes"). Collapsing whitespace to single spaces makes phrase
    assertions robust to line-wrap position while still failing if the
    words themselves change or move to a different sentence.
    """
    return " ".join(_read_skill().split())


def _assert_present(haystack: str, needle: str, reason: str) -> None:
    """One-line assertion helper: `needle` must appear in `haystack`."""
    assert needle in haystack, reason


def _assert_absent(haystack: str, needle: str, reason: str) -> None:
    """One-line assertion helper: `needle` must NOT appear in `haystack`."""
    assert needle not in haystack, reason


def _frontmatter_block() -> str:
    match = _FRONTMATTER.search(_read_skill())
    assert match is not None, "SKILL.md must open with a --- frontmatter block"
    return match.group(1)


def test_skill_md_exists() -> None:
    # Arrange / Act / Assert
    assert SKILL_MD.is_file(), f"missing SKILL.md at {SKILL_MD}"


def test_repo_root_resolves_to_true_root_not_a_fixed_parent_depth() -> None:
    """Regression guard: `_find_repo_root` must not regress to `parents[N]`.

    This module is mirrored into `src/copilot-cli/skills/memory-consolidate/
    tests/`, three directories deeper than the canonical
    `.claude/skills/memory-consolidate/tests/` copy. A fixed `parents[2]`
    (the prior implementation) resolved correctly only from the canonical
    path; from the mirror it landed on `src/` and silently pointed
    `MEMORY_README` at a path that does not exist there, so any test
    reading it would fail with a confusing "missing canonical README"
    error. This test pins the marker-based fix, independent of which copy
    of this file pytest happens to collect.
    """
    # Arrange / Act
    resolved = _find_repo_root(SKILL_DIR)

    # Assert: the true repo root is the one and only ancestor holding both
    # pyproject.toml and the .serena memory tree this skill documents.
    assert (resolved / "pyproject.toml").is_file(), (
        f"_find_repo_root resolved to {resolved}, which has no pyproject.toml; "
        "it must anchor on the ancestor that actually carries the marker, "
        "not a fixed parents[N] index that differs between the canonical "
        "skill path and its src/copilot-cli mirror"
    )
    assert (resolved / ".serena" / "memories" / "README.md").is_file(), (
        f"_find_repo_root resolved to {resolved}, which has no "
        ".serena/memories/README.md; REPO_ROOT must point at the true repo "
        "root in both the canonical tree and the mirrored tree"
    )


def test_frontmatter_has_required_fields() -> None:
    # Arrange
    block = _frontmatter_block()

    # Act / Assert
    assert re.search(r"^name:\s*memory-consolidate\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly memory-consolidate"
    )
    assert re.search(r"^description:\s*\S", block, re.MULTILINE) or re.search(
        r"^description:\s*[>|]", block, re.MULTILINE
    ), "description required"


def test_skill_under_size_ceiling() -> None:
    # Arrange
    line_count = len(_read_skill().splitlines())

    # Act / Assert
    assert line_count <= 500, f"SKILL.md is {line_count} lines, ceiling is 500"


def test_description_names_durable_and_dated_split() -> None:
    # Arrange
    block = _frontmatter_block().lower()

    # Act / Assert: the description must name the operation's core split.
    assert "durable" in block, "description must name the durable-context concept"
    assert "dated" in block, "description must name the dated-context concept"


def test_description_has_three_to_five_backtick_triggers() -> None:
    # Arrange: SkillForge requires 3 to 5 backtick-wrapped trigger phrases.
    block = _frontmatter_block()
    triggers = _BACKTICK_TRIGGER.findall(block)

    # Act / Assert
    assert 3 <= len(triggers) <= 5, (
        f"expected 3 to 5 backtick trigger phrases, found {len(triggers)}: {triggers}"
    )


def test_description_do_not_clause_names_siblings_without_backticks() -> None:
    # Arrange: sibling skills (memory-search, memory-maintenance, memory-gate,
    # memory-reflexion) name the alternative skill in the Do NOT clause
    # WITHOUT backticks, so the trigger count above stays accurate. A
    # backtick-wrapped skill name here would silently inflate the trigger
    # count past 5 without failing the count check on its own.
    block = _frontmatter_block()

    # Act / Assert
    assert "(use curating-memories)" in block, (
        "Do NOT clause must name curating-memories without backticks"
    )
    assert "(use memory-maintenance)" in block, (
        "Do NOT clause must name memory-maintenance without backticks"
    )


def test_points_at_canonical_supersession_sweep() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: Phase 1 delegates staleness classification to the
    # existing curating-memories script; it does not reimplement it.
    assert "skills/curating-memories/scripts" in body, (
        "memory-consolidate must reference the curating-memories scripts directory"
    )
    assert "supersession_sweep.py" in body, (
        "memory-consolidate must delegate to the canonical supersession_sweep.py"
    )


def test_points_at_canonical_size_scripts() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: Phase 1 and the Verification table confirm thinness and
    # oversize with the canonical memory-maintenance scripts, not by eye.
    assert "count_memory_tokens.py" in body, (
        "memory-consolidate must delegate to the canonical count_memory_tokens.py"
    )
    assert "test_memory_size.py" in body, (
        "memory-consolidate must delegate to the canonical test_memory_size.py"
    )


def test_uses_portable_script_root() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: executable invocations must resolve the plugin root
    # through the harness env var so a vendored install works
    # (check_skill_md_exec_portability).
    assert "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}" in body, (
        "memory-consolidate must invoke scripts through the portable plugin-root form"
    )


def test_process_section_has_three_named_phases() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: matches the ### Phase N heading shape SkillForge's
    # Process-section check requires, and pins the three phases the plan
    # committed to (Take Stock, Consolidate, Tidy the Index).
    assert "## Process" in body, "SKILL.md must have a ## Process section"
    assert re.search(r"^### Phase 1: Take Stock", body, re.MULTILINE), (
        "Phase 1 must be titled 'Take Stock'"
    )
    assert re.search(r"^### Phase 2: Consolidate", body, re.MULTILINE), (
        "Phase 2 must be titled 'Consolidate'"
    )
    assert re.search(r"^### Phase 3: Tidy the Index", body, re.MULTILINE), (
        "Phase 3 must be titled 'Tidy the Index'"
    )


def test_size_constraints_table_not_duplicated_but_referenced() -> None:
    """Prompt-review MEDIUM finding: do not duplicate README.md's table.

    The table used to be quoted verbatim in SKILL.md, duplicating canonical
    content that drifts silently the moment README.md's numbers change. This
    test asserts the inverse: the table shape must NOT appear in SKILL.md,
    and a reference to README.md's "Size Constraints" section must.
    """
    # Arrange
    body = _read_skill()

    # Act / Assert: the pipe-table shape is gone, the reference remains.
    assert _SIZE_TABLE_ROW.search(body) is None, "must not duplicate the Size Constraints table"
    _assert_present(body, "Size Constraints", "must still reference README.md's section")


def test_sweep_buckets_not_enumerated_links_to_curating_memories() -> None:
    """Prompt-review MEDIUM finding: do not duplicate the sweep's bucket list.

    SKILL.md used to restate all four bucket names, duplicating the table
    `curating-memories/SKILL.md` already owns. `temporal-snapshot-as-live`
    is the most distinctive name, so its absence is the signal the
    duplicate enumeration is gone; a reference to curating-memories' own
    bucket documentation must remain in its place.
    """
    # Arrange
    body = _read_skill()

    # Act / Assert
    _assert_absent(body, "temporal-snapshot-as-live", "must not re-enumerate the four buckets")
    _assert_present(body.lower(), "four buckets", "must reference curating-memories' buckets")


def test_serena_list_scope_matches_readme_verbatim() -> None:
    """Canonical-source-mirror guard: `list_memories` scope must match README.md.

    `.serena/memories/README.md` ("Directory Structure") draws a hard line:
    `list_memories` shows top-level index and special files only, and every
    atomic topic memory lives in a subdirectory that `list_memories` does
    not enumerate. A prior draft of this skill listed `mcp__serena__list_memories`
    next to a plain `ls .serena/memories` as if either one surfaced the full
    memory tree, which would send an agent looking for atomic topic files
    that `list_memories` cannot show it. This test re-reads README.md at test
    time and requires the SKILL.md body to state the same limitation, so a
    future rewrite of the Tool Order section cannot silently drop the
    clarification.
    """
    # Arrange
    assert MEMORY_README.is_file(), f"missing canonical README at {MEMORY_README}"
    readme_text = MEMORY_README.read_text(encoding="utf-8")
    body = _read_skill()

    # Act / Assert: README.md actually draws this distinction (guards against
    # the check itself going stale if README.md's wording changes shape).
    assert "visible in `list_memories`" in readme_text, (
        "README.md no longer documents the list_memories top-level-only "
        "scope in the expected shape; re-verify and update this test"
    )
    assert "hidden from `list_memories`" in readme_text, (
        "README.md no longer documents that subdirectories are hidden from "
        "list_memories; re-verify and update this test"
    )

    # Act / Assert: SKILL.md must state the same limitation, not imply
    # list_memories enumerates atomic topic files.
    assert "top-level files only" in body or "top-level only" in body, (
        "SKILL.md must state that mcp__serena__list_memories enumerates "
        "top-level (index) files only, matching .serena/memories/README.md"
    )
    assert "hidden from" in body, (
        "SKILL.md must state that atomic topic memories in subdirectories "
        "are hidden from list_memories, matching .serena/memories/README.md"
    )
    assert "*-index.md" in body, (
        "SKILL.md must direct the reader to topic index files (not just "
        "the top-level memory-index.md) to find atomic memory paths, since "
        "list_memories alone cannot surface them"
    )


def test_tool_order_does_not_quote_readme_verbatim() -> None:
    """MEDIUM prompt-review finding: Tool Order must not re-quote README.md.

    A prior draft of Tool Order tier 2 quoted README.md's "Directory
    Structure" sentences verbatim, in full, with their own quotation marks
    ("**Top-level** (visible in `list_memories`): ..."). That duplicates
    canonical contract text inside SKILL.md, so the two copies can drift
    the moment README.md's wording changes. This test asserts the quote is
    gone and that the indexes-only mechanic is stated exactly once, in
    Phase 1, while Tool Order tier 2 only points at README.md and Phase 1.
    """
    # Arrange
    body = _read_skill()

    # Act / Assert: the verbatim quoted sentence opening is gone.
    _assert_absent(
        body,
        "**Top-level** (visible in",
        "Tool Order must not quote README.md's Directory Structure sentence verbatim",
    )
    _assert_absent(
        body,
        "**Subdirectories** (hidden from",
        "Tool Order must not quote README.md's Directory Structure sentence verbatim",
    )

    # Act / Assert: the mechanic is stated exactly once, and it lives in
    # Phase 1, not duplicated across Tool Order and Phase 1.
    assert body.count("top-level files only") == 1, (
        "'top-level files only' must appear exactly once (in Phase 1), not "
        "restated in Tool Order tier 2 as well"
    )


def test_index_budget_is_not_misattributed_to_readme() -> None:
    # Arrange: the 200-line / 25 KB index budget is this skill's own
    # operational target, not a claim sourced from README.md (which sets no
    # such number for the top-level index). The prose must say so explicitly
    # so a reader does not treat it as a canonical-source-mirror claim.
    body = _read_skill()

    # Act / Assert
    assert "this skill's own operational budget" in body.lower() or (
        "own operational budget" in body.lower()
    ), (
        "the 200-line/25KB index budget must be framed as this skill's own "
        "target, not attributed to README.md"
    )


def test_never_claims_authority_to_physically_delete() -> None:
    """CRITICAL prompt-review finding: no self-authorized hard deletion.

    An earlier draft said this operation "does not add a second,
    proposal-only approval gate" on top of the write conventions, then
    instructed deleting the poorer file directly: a self-authorized
    deletion path with no independent check. This test asserts the
    corrected claim: physical deletion is never performed by this skill and
    always requires a separate human-confirmed or independently
    second-checked ratification step.
    """
    # Arrange
    lowered = _read_skill_unwrapped().lower()

    # Act / Assert: the corrected claim is present.
    _assert_present(lowered, "never physically deletes", "must state it never deletes")
    _assert_present(lowered, "ratification", "must require a ratification step")
    _assert_present(lowered, "human-confirmed", "must name a human-confirmed gate")

    # Act / Assert: the old self-authorization claim is gone.
    _assert_absent(lowered, "does not add a second", "must not claim self-granted authority")
    _assert_absent(
        lowered,
        "approval gate on top of the existing write conventions",
        "must not frame ratification as an anti-pattern to route around",
    )


def test_no_dangling_supersedes_references() -> None:
    # Arrange: a supersedes relation must never point at a file this skill
    # deleted, because this skill deletes nothing; if a later, separately
    # ratified change removes a file, that change (not this skill) must
    # update every reference that pointed at it.
    body = _read_skill_unwrapped().lower()

    # Act / Assert
    _assert_present(body, "dangling", "must prohibit dangling supersedes references")
    assert "still exists" in body or "still on disk" in body, (
        "SKILL.md must state the supersedes target stays on disk, not deleted"
    )


def test_merge_boundary_same_entity_only() -> None:
    # Arrange: the merge boundary must name the constraint explicitly, not
    # leave "overlapping" ambiguous enough to license merging unrelated
    # concepts that merely share a domain or index section.
    body = _read_skill_unwrapped().lower()

    # Act / Assert
    _assert_present(body, "genuine duplicate", "must bound merging to genuine duplicates")
    _assert_present(body, "distinct atomic concepts", "must forbid combining distinct concepts")


def test_date_anchor_is_observation_stamp_or_file_history_not_session_date() -> None:
    """HIGH prompt-review finding: never resolve dates against today.

    An earlier draft resolved every relative date "against the current
    session date," which would silently shift dates forward by however long
    passed since the memory was written. This asserts the corrected anchor
    (the observation's own timestamp or file history) is documented, the
    old session-date anchor is gone, and an unanchored date is flagged
    rather than guessed.
    """
    # Arrange
    lowered = _read_skill_unwrapped().lower()

    # Act / Assert: the corrected anchor is present.
    assert "source stamp" in lowered or "[yyyy-mm-dd]" in lowered, (
        "SKILL.md must anchor date resolution on the observation's source stamp"
    )
    _assert_present(lowered, "file history", "must offer file history as fallback anchor")
    _assert_present(lowered, "ambiguous-date", "must flag an unanchored date instead of guessing")

    # Act / Assert: the old wall-clock anchor is gone.
    _assert_absent(
        lowered,
        "against the current session date",
        "must not anchor date resolution on the session's wall-clock date",
    )


def test_discovery_tiers_separated_from_canonical_scripts() -> None:
    # Arrange: the Tool Order's three-tier fallback governs discovery only;
    # the canonical scripts (sweep, token count, size check) must be stated
    # as running regardless of which tier surfaced the file list, not as a
    # fourth fallback tier.
    body = _read_skill_unwrapped().lower()

    # Act / Assert
    _assert_present(body, "discovery only", "must state the tiers govern discovery only")
    _assert_present(body, "regardless of which", "must state scripts run regardless of tier")


def test_no_forbidden_dash_characters() -> None:
    # Arrange: repo-wide voice rule forbids em dash and en dash characters.
    body = _read_skill()

    # Act / Assert
    assert "\u2014" not in body, "SKILL.md must not contain an em dash"
    assert "\u2013" not in body, "SKILL.md must not contain an en dash"


@pytest.mark.parametrize(
    "term",
    ["overlap", "richer path", "absolute date", "supersedes"],
)
def test_carries_consolidation_operation_concepts(term: str) -> None:
    # Arrange: the sub-skill must be a deep module (carry the consolidation
    # decision knowledge), not a one-line pass-through to the router.
    body = _read_skill().lower()

    # Act / Assert
    assert term in body, f"memory-consolidate must describe the {term!r} concept"


def test_links_related_skills() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the Related Skills table must route a caller to the
    # correct sibling instead of loading memory-consolidate by mistake.
    for sibling in ("memory-maintenance", "memory-search", "curating-memories"):
        assert sibling in body, f"Related Skills must list {sibling}"


def test_frontmatter_declares_adr_056() -> None:
    # Arrange: ADR-063 requires every decomposed sub-skill to emit ADR-056's
    # standard output envelope (`.agents/architecture/
    # ADR-063-memory-skill-decomposition.md`, point 4: "Every sub-skill
    # emits the standard output envelope (ADR-056)"). `memory-reflexion`,
    # the sibling this skill matches, declares ADR-056 in its own
    # `metadata.adr` frontmatter field.
    block = _frontmatter_block()

    # Act / Assert
    assert re.search(r"^\s*adr:.*ADR-056", block, re.MULTILINE), (
        "frontmatter metadata.adr must include ADR-056, matching "
        "memory-reflexion and the ADR-063 sub-skill requirement"
    )


def test_output_section_states_adr_056_envelope_once() -> None:
    """MEDIUM prompt-review finding: emit ADR-056's envelope, not duplicated.

    ADR-063 requires every decomposed sub-skill to emit ADR-056's standard
    output envelope. This test asserts a single `## Output` section names
    all four ADR-056 fields (Success, Data, Error, Metadata) and that the
    prior Phase 3 closing paragraph was folded into it rather than left as
    a second, separate output-reporting section.
    """
    # Arrange
    body = _read_skill()

    # Act / Assert: exactly one Output section, naming all four fields.
    assert body.count("## Output") == 1, "must have exactly one ## Output section"
    for field in ("Success", "Data", "Error", "Metadata"):
        assert f"**{field}**" in body, f"Output section must name the {field} envelope field"

    # Act / Assert: the old duplicate closing-summary phrasing is gone; the
    # files-touched summary now lives inside Output, referenced once.
    _assert_absent(
        body,
        "Finish with a short summary",
        "the closing summary must live in the Output section, not restated a second time",
    )
