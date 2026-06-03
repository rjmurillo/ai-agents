#!/usr/bin/env python3
"""Structural tests for the retrospective skill decomposition (issue #2080, PR 1 of N).

This PR creates the skill contract only: `.claude/skills/retrospective/SKILL.md`
plus three `references/` files lifted verbatim from the source agent body. Scripts,
agent deletion, and template removal are out of scope for this slice.

These tests pin the structural contract that the SkillForge validator, the skill-size
gate, and the canonical-source-mirror rule depend on:

- The SKILL.md exists at the canonical path with valid frontmatter (name, version,
  description) per `.agents/steering/claude-skills.md`.
- The Triggers section has 1 to 5 backtick-wrapped trigger phrases (SkillForge
  `validate_triggers` contract).
- The Process section orchestrates the fixed Phase 0 through Phase 5 workflow.
- A Success Criteria (Verification) section with checkboxes exists (SkillForge
  `validate_verification` contract).
- The three reference files exist and are linked from SKILL.md.
- The rubrics in the references are byte-faithful to the source agent body
  (`.claude/agents/retrospective.md`), per the canonical-source-mirror rule.
- No file carries an em-dash (U+2014) or en-dash (U+2013) per universal.md.
- The `scripts/` directory ships the PR 2 atomicity/evidence/orchestration scripts.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "retrospective"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"
FRAMEWORKS = REFERENCES_DIR / "frameworks.md"
LEARNING_TEMPLATE = REFERENCES_DIR / "learning-template.md"
DIAGNOSIS_ACTIONS = REFERENCES_DIR / "diagnosis-and-actions.md"
SOURCE_AGENT = PROJECT_ROOT / ".claude" / "agents" / "retrospective.md"

# U+2014 em-dash, U+2013 en-dash. Banned by .claude/rules/universal.md.
_DASH_PATTERN = re.compile("[\\u2013\\u2014]")
# Mirrors SkillForge validate-skill.py:validate_triggers backtick extraction.
_BACKTICK = re.compile(r"`([^`]+)`")


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_MD.is_file(), f"SKILL.md not found at canonical path: {SKILL_MD}"
    return SKILL_MD.read_text(encoding="utf-8")


def _triggers_section(content: str) -> str:
    """Extract the Triggers section, mirroring the SkillForge validator regex."""
    match = re.search(
        r"##\s*Triggers\s*\n(.*?)(?=\n##|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    assert match is not None, "Missing Triggers section"
    return match.group(1)


class TestExistenceAndLayout:
    def test_skill_md_exists(self) -> None:
        assert SKILL_MD.is_file()

    def test_references_directory_exists(self) -> None:
        assert REFERENCES_DIR.is_dir()

    @pytest.mark.parametrize(
        "ref_path",
        [FRAMEWORKS, LEARNING_TEMPLATE, DIAGNOSIS_ACTIONS],
    )
    def test_reference_file_exists(self, ref_path: Path) -> None:
        assert ref_path.is_file(), f"missing reference file: {ref_path.name}"

    def test_slice_ships_scripts_directory(self) -> None:
        # PR 2 adds the script layer; the PR 1 forward-guard is now satisfied.
        scripts_dir = SKILL_DIR / "scripts"
        assert scripts_dir.is_dir(), "PR 2 ships the scripts/ directory"
        for script in ("score_atomicity.py", "extract_evidence.py", "run_retrospective.py"):
            assert (scripts_dir / script).is_file(), f"PR 2 ships scripts/{script}"


class TestFrontmatter:
    def test_frontmatter_starts_on_line_one(self, skill_text: str) -> None:
        assert skill_text.startswith("---\n")

    @pytest.mark.parametrize("field", ["name", "version", "description"])
    def test_required_frontmatter_field_present(self, skill_text: str, field: str) -> None:
        front = skill_text.split("---", 2)[1]
        assert re.search(rf"(?m)^{field}:\s*\S", front), f"missing frontmatter field: {field}"

    def test_name_matches_directory(self, skill_text: str) -> None:
        front = skill_text.split("---", 2)[1]
        match = re.search(r"(?m)^name:\s*(\S+)", front)
        assert match is not None
        assert match.group(1) == "retrospective"

    def test_version_is_semver(self, skill_text: str) -> None:
        front = skill_text.split("---", 2)[1]
        match = re.search(r"(?m)^version:\s*(\S+)", front)
        assert match is not None
        assert re.fullmatch(r"\d+\.\d+\.\d+", match.group(1)), match.group(1)


class TestTriggers:
    def test_trigger_count_in_range(self, skill_text: str) -> None:
        # SkillForge contract: 1 to 5 backtick-wrapped phrases in the section.
        phrases = _BACKTICK.findall(_triggers_section(skill_text))
        assert 1 <= len(phrases) <= 5, f"found {len(phrases)} trigger phrases"

    def test_retro_fill_trigger_present(self, skill_text: str) -> None:
        # #2079 invokes the skill from `/retro fill <date>`; the trigger must exist.
        phrases = _BACKTICK.findall(_triggers_section(skill_text))
        assert any("retro fill" in p for p in phrases)

    def test_triggers_have_no_shell_metacharacters(self, skill_text: str) -> None:
        # Negative: CWE-94 mitigation in the validator rejects shell metacharacters.
        phrases = _BACKTICK.findall(_triggers_section(skill_text))
        safe = re.compile(r"^[a-zA-Z0-9 \-_.,]+$")
        unsafe = [p for p in phrases if not safe.match(p)]
        assert unsafe == [], f"unsafe trigger phrases: {unsafe}"


class TestProcessOrchestration:
    @pytest.mark.parametrize("phase", range(6))
    def test_phase_heading_present(self, skill_text: str, phase: int) -> None:
        # The binding decision: orchestrate Phase 0 through Phase 5.
        assert re.search(rf"(?m)^###\s*Phase\s*{phase}\b", skill_text), (
            f"missing Phase {phase} heading"
        )

    def test_has_process_section(self, skill_text: str) -> None:
        assert re.search(r"(?m)^##\s*Process\b", skill_text)

    def test_has_success_criteria_section_with_checkboxes(self, skill_text: str) -> None:
        # SkillForge validate_verification: needs a Verification/Success Criteria/
        # Checklist heading and at least 2 checkboxes.
        assert re.search(r"(?m)^##\s*(Verification|Success Criteria|Checklist)\b", skill_text)
        assert len(re.findall(r"\[\s*\]", skill_text)) >= 2


class TestReferenceLinks:
    @pytest.mark.parametrize(
        "ref_name",
        ["frameworks.md", "learning-template.md", "diagnosis-and-actions.md"],
    )
    def test_skill_links_each_reference(self, skill_text: str, ref_name: str) -> None:
        assert f"references/{ref_name}" in skill_text, (
            f"SKILL.md does not link references/{ref_name}"
        )


class TestCanonicalSourceFidelity:
    """The references claim to lift rubrics verbatim from the source agent body.

    Each anchor below is a load-bearing string that must appear identically in the
    source agent and in the reference that claims to mirror it. A drift here is the
    confident-incorrectness failure the canonical-source-mirror rule guards against.
    """

    def test_source_agent_exists(self) -> None:
        assert SOURCE_AGENT.is_file()

    @pytest.mark.parametrize(
        "anchor",
        [
            "What did you see and hear?",
            "Insufficient research scope",
            "Mad (Blocked)",
            "Redis cache with 5-min TTL reduced API calls by 73% for user profiles",
        ],
    )
    def test_anchor_present_in_source(self, anchor: str) -> None:
        assert anchor in SOURCE_AGENT.read_text(encoding="utf-8")

    def test_frameworks_mirror_anchors_verbatim(self) -> None:
        text = FRAMEWORKS.read_text(encoding="utf-8")
        assert "What did you see and hear?" in text
        assert "Insufficient research scope" in text

    def test_diagnosis_mirrors_anchors_verbatim(self) -> None:
        text = DIAGNOSIS_ACTIONS.read_text(encoding="utf-8")
        assert "Redis cache with 5-min TTL reduced API calls by 73% for user profiles" in text
        assert 'Compound statements ("and", "also")' in text

    def test_learning_template_mirrors_artifact_skeleton_verbatim(self) -> None:
        text = LEARNING_TEMPLATE.read_text(encoding="utf-8")
        assert "# Retrospective: [Scope]" in text
        assert "## Phase 4: Extracted Learnings" in text
        assert "## Deduplication Check" in text

    @pytest.mark.parametrize(
        "ref_path",
        [FRAMEWORKS, LEARNING_TEMPLATE, DIAGNOSIS_ACTIONS],
    )
    def test_reference_cites_canonical_source_path(self, ref_path: Path) -> None:
        # canonical-source-mirror: the first commit must cite the source path verbatim.
        assert ".claude/agents/retrospective.md" in ref_path.read_text(encoding="utf-8")


class TestNoDashes:
    @pytest.mark.parametrize(
        "path",
        [SKILL_MD, FRAMEWORKS, LEARNING_TEMPLATE, DIAGNOSIS_ACTIONS],
    )
    def test_contains_no_em_or_en_dash(self, path: Path) -> None:
        match = _DASH_PATTERN.search(path.read_text(encoding="utf-8"))
        assert match is None, (
            f"prohibited dash in {path.name} at offset {match.start()}" if match else ""
        )
