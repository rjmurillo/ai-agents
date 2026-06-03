"""Contract tests for the ontology elicitation step in the /spec pipeline.

Pins issue #1925: the /spec pipeline must elicit a domain ontology before
requirements are written, carry the OntologyFragment into the spec-generator
PRD contract, and fold an ontology-coverage check into the completeness gate.

These tests are structural, not behavioral. The contract is consumed by an
LLM-driven agent (the /spec command, the spec-generator skill, the
completeness-check prompt), not by code. Structural verification asserts the
contract fragments are present and well-formed and that the documented
boundaries hold:

- The ontology step is a SUB-STEP of Step 1, not a new top-level step. Step 0
  First Principles already owns the front of the pipeline, and renumbering the
  ordered Steps 1-9 (which reference each other by number) is forbidden by the
  issue's scope notes.
- The completeness check folds ontology coverage into PASS/PARTIAL/FAIL and
  MUST NOT introduce a new top-level verdict token (the CI extractor in
  `.github/actions/ai-review/action.yml` anchors on PASS|PARTIAL|FAIL only).
- Empty-entity features degrade gracefully with no spurious FAIL.

The Claude canonical sources are tested. The Copilot twins are generated from
them by `build/scripts/generate_skills.py` / `generate_commands.py`; their drift
is guarded by `test_lifecycle_command_drift.py` and the build pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / ".claude" / "commands" / "spec.md"
GENERATOR_PATH = REPO_ROOT / ".claude" / "skills" / "spec-generator" / "SKILL.md"
COMPLETENESS_PATH = REPO_ROOT / ".github" / "prompts" / "spec-check-completeness.md"
REFERENCE_FRAGMENT = (
    REPO_ROOT / ".agents" / "specs" / "ontology" / "spec-ontology-elicitation.md"
)

ONTOLOGY_PROMPTS = ["O1", "O2", "O3", "O4", "O5", "O6", "O7"]


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def generator_text() -> str:
    return GENERATOR_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def completeness_text() -> str:
    return COMPLETENESS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step_1_region(spec_text: str) -> str:
    """Return the substring covering Step 1 of /spec.

    Step 1 begins at the ordered-list item `1. Clarify the problem.` and ends
    at the next top-level item (`2.`). The ontology sub-step must live inside
    this region (it is a Step 1 sub-step, not a new top-level step).
    """
    start = spec_text.find("1. Clarify the problem.")
    assert start != -1, "Step 1 anchor not found in spec.md"
    end = spec_text.find("\n2. ", start)
    assert end != -1, "Step 1 has no terminator (`\\n2. `)"
    return spec_text[start:end]


@pytest.fixture(scope="module")
def step_6_region(spec_text: str) -> str:
    """Return the substring covering Step 6 of /spec (the spec-generator call)."""
    start = spec_text.find("6. **Formalize the PRD into durable artifacts**")
    assert start != -1, "Step 6 anchor not found in spec.md"
    end_candidates = [spec_text.find("\n7.", start), spec_text.find("\n## ", start)]
    end_candidates = [c for c in end_candidates if c != -1]
    assert end_candidates, "Step 6 has no terminator"
    return spec_text[start : min(end_candidates)]


# --- Positive: the ontology elicitation step exists and is well-formed ---


def test_ontology_substep_present_in_step_1(step_1_region: str) -> None:
    """The ontology elicitation sub-step lives inside Step 1 (Clarify)."""
    assert "#### Step 1 Ontology elicitation" in step_1_region, (
        "Step 1 of spec.md missing the `#### Step 1 Ontology elicitation` sub-step"
    )


def test_ontology_substep_lists_all_seven_prompts(step_1_region: str) -> None:
    """All seven ontology prompts O1..O7 are elicited, by label."""
    for prompt in ONTOLOGY_PROMPTS:
        assert re.search(rf"\*\*{prompt} ", step_1_region), (
            f"Step 1 ontology elicitation missing prompt label {prompt}"
        )


def test_ontology_substep_covers_ddd_concepts(step_1_region: str) -> None:
    """The seven prompts cover the DDD concepts the issue named.

    Entities, ubiquitous language / names, relationships, aggregate boundaries,
    decision rules, bounded-context boundaries, open ontology questions.
    """
    lowered = step_1_region.lower()
    required_concepts = [
        "entit",  # entities / entity
        "ubiquitous language",
        "relationship",
        "aggregate",
        "decision rule",
        "bounded-context",
        "open ontology question",
    ]
    for concept in required_concepts:
        assert concept in lowered, (
            f"Step 1 ontology elicitation must cover DDD concept: {concept!r}"
        )


def test_ontology_fragment_output_path_documented(step_1_region: str) -> None:
    """The OntologyFragment is written to the canonical ontology directory."""
    assert ".agents/specs/ontology/" in step_1_region, (
        "Step 1 ontology elicitation must name the `.agents/specs/ontology/` "
        "output directory for the OntologyFragment"
    )


def test_ontology_fragment_carried_into_step_6(step_6_region: str) -> None:
    """Step 6 passes the OntologyFragment into the spec-generator PRD contract."""
    assert "OntologyFragment" in step_6_region, (
        "Step 6 must pass the OntologyFragment to spec-generator"
    )
    assert ".agents/specs/ontology/" in step_6_region, (
        "Step 6 must name the OntologyFragment path passed to spec-generator"
    )


def test_ontology_in_prd_output_schema(spec_text: str) -> None:
    """The PRD output schema lists an Ontology section."""
    # The output schema is a bulleted list near the end of the file.
    assert "- **Ontology**" in spec_text, (
        "PRD output schema must include an `- **Ontology**` entry"
    )


# --- Positive: spec-generator accepts the fragment and renders the section ---


def test_generator_documents_ontology_section(generator_text: str) -> None:
    """spec-generator renders an `## Ontology` body section per requirement."""
    assert "## Ontology" in generator_text, (
        "spec-generator SKILL.md must document the `## Ontology` body section"
    )
    assert "OntologyFragment" in generator_text, (
        "spec-generator SKILL.md must reference the OntologyFragment as input"
    )


def test_generator_requirement_body_includes_ontology(generator_text: str) -> None:
    """The Requirement Structure body lists the Ontology item between Context
    and Acceptance Criteria."""
    body_start = generator_text.find("### Requirement Structure")
    assert body_start != -1, "Requirement Structure heading not found"
    next_heading = generator_text.find("\n### ", body_start + 1)
    region = generator_text[body_start:next_heading]
    context_pos = region.find("Context")
    ontology_pos = region.find("Ontology")
    ac_pos = region.find("Acceptance Criteria")
    assert -1 < context_pos < ontology_pos < ac_pos, (
        "Requirement body must order: Context, then Ontology, then "
        "Acceptance Criteria"
    )


def test_generator_requires_canonical_name_reuse(generator_text: str) -> None:
    """spec-generator must reference entities by their O2 canonical name."""
    lowered = generator_text.lower()
    assert "canonical name" in lowered, (
        "spec-generator must require entities be named by their canonical O2 name"
    )


# --- Negative: no new top-level step, no new verdict token ---


def test_no_literal_phase_0_added(spec_text: str) -> None:
    """The issue's 'Phase 0' premise is rejected: no literal Phase 0 before
    Step 0. Step 0 First Principles already owns the front of the pipeline."""
    assert "Phase 0" not in spec_text, (
        "spec.md must not introduce a literal 'Phase 0'; Step 0 owns the front"
    )


def test_ontology_step_is_not_a_new_top_level_step(spec_text: str) -> None:
    """The ontology step does not renumber the pipeline.

    No `### Step 1.5` heading and no new top-level ordered item: downstream
    steps reference each other by number, so renumbering is forbidden. The
    ontology elicitation is a Step 1 sub-step (h4), not a top-level step.
    """
    assert "### Step 1.5" not in spec_text, (
        "ontology step must not be a new top-level `### Step 1.5` block"
    )
    # The top-level ordered list still ends at Step 9 (the critic step). A new
    # top-level step would have introduced a `10.` item.
    assert not re.search(r"^10\.\s", spec_text, re.MULTILINE), (
        "ontology step must not add a 10th top-level step"
    )


def test_completeness_check_no_new_verdict_token(completeness_text: str) -> None:
    """The completeness check folds ontology coverage into PASS/PARTIAL/FAIL;
    it MUST NOT introduce a new top-level token the CI extractor cannot match."""
    # The only verdict tokens emitted on a literal `VERDICT:` line are the three
    # the CI extractor knows. An ONTOLOGY-INCOMPLETE token must not appear as a
    # verdict line.
    assert not re.search(r"VERDICT:\s*ONTOLOGY", completeness_text), (
        "completeness check must not emit a new ONTOLOGY-* verdict token"
    )
    # The three canonical tokens remain the only verdict vocabulary.
    for token in ("PASS", "PARTIAL", "FAIL"):
        assert f"VERDICT: {token}" in completeness_text, (
            f"completeness check lost the canonical `VERDICT: {token}` token"
        )


def test_completeness_check_folds_ontology_into_verdict(completeness_text: str) -> None:
    """Ontology coverage and decision-rule traceability are documented as
    PARTIAL/FAIL criteria, not as a standalone gate."""
    lowered = completeness_text.lower()
    assert "ontology coverage" in lowered, (
        "completeness check must document an ontology-coverage check"
    )
    assert "entity coverage" in lowered, (
        "completeness check must document entity coverage"
    )
    assert "traceability" in lowered, (
        "completeness check must document decision-rule traceability"
    )
    # The unnamed-primary-entity case must lean FAIL.
    fail_idx = lowered.find("`fail`: critical")
    assert fail_idx != -1, "FAIL verdict guideline not found"
    fail_region = lowered[fail_idx : fail_idx + 400]
    assert "entity" in fail_region and "ontology" in fail_region, (
        "FAIL guideline must name the absent-primary-entity ontology gap"
    )


# --- Edge: empty / no-entity feature degrades without a spurious failure ---


def test_empty_entity_feature_degrades_in_step_1(step_1_region: str) -> None:
    """A feature with no domain entities still emits a (trivial) fragment."""
    lowered = step_1_region.lower()
    assert "no domain entit" in lowered, (
        "Step 1 must document the empty-entity (no domain entities) degradation"
    )
    assert "shall not" in lowered or "not produce a step 7" in lowered, (
        "Step 1 must state an empty-entity feature does not produce a FAIL"
    )


def test_completeness_check_no_spurious_fail_when_no_ontology(
    completeness_text: str,
) -> None:
    """Absence of an ontology, or an empty-entity ontology, must not lower the
    verdict."""
    lowered = completeness_text.lower()
    assert "vacuously satisfied" in lowered, (
        "completeness check must mark empty-entity coverage as vacuously satisfied"
    )
    assert "n/a" in lowered, (
        "completeness check must mark a missing ontology as N/A, not a gap"
    )


def test_ontology_fragment_never_halts(spec_text: str) -> None:
    """The OntologyFragment is never a halt condition (graceful degradation)."""
    # The Step 1 sub-step explicitly states the fragment is never a halt.
    assert "never a halt" in spec_text.lower(), (
        "Step 1 ontology elicitation must state the OntologyFragment is never a halt"
    )


# --- Reference fragment runs end-to-end (acceptance criterion 6) ---


def test_reference_fragment_exists_and_has_seven_sections() -> None:
    """A reference OntologyFragment is checked in and has all seven O sections."""
    assert REFERENCE_FRAGMENT.is_file(), (
        f"reference OntologyFragment missing at {REFERENCE_FRAGMENT}"
    )
    text = REFERENCE_FRAGMENT.read_text(encoding="utf-8")
    for prompt in ONTOLOGY_PROMPTS:
        assert re.search(rf"^## {prompt} ", text, re.MULTILINE), (
            f"reference OntologyFragment missing `## {prompt}` section"
        )


def test_reference_fragment_slug_matches_directory_convention() -> None:
    """The reference fragment lives under the canonical ontology directory with
    a kebab-case slug (the same slug convention spec-generator uses)."""
    assert REFERENCE_FRAGMENT.parent == (
        REPO_ROOT / ".agents" / "specs" / "ontology"
    ), "reference fragment must live under .agents/specs/ontology/"
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", REFERENCE_FRAGMENT.stem), (
        f"reference fragment slug {REFERENCE_FRAGMENT.stem!r} must be kebab-case"
    )
