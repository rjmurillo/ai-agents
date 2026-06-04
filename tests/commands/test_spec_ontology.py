"""Contract tests for the ontology elicitation step in the /spec pipeline.

Tests the safe #1925 ontology slice: the /spec pipeline must elicit a domain
ontology before requirements are written, carry the OntologyFragment into the
spec-generator PRD contract, and fold an ontology-coverage check into the
completeness gate without adding a new verdict token.

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
  MUST NOT introduce a new top-level verdict token without a coordinated
  `.github/actions/ai-review/action.yml` allowlist update.
- Empty-entity features degrade gracefully with no spurious FAIL.

The Claude canonical sources are tested. The Copilot twins are generated from
them by `build/scripts/generate_skills.py` / `build/scripts/generate_commands.py`;
their drift is guarded by `test_lifecycle_command_drift.py` and the build pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / ".claude" / "commands" / "spec.md"
GENERATOR_PATH = REPO_ROOT / ".claude" / "skills" / "spec-generator" / "SKILL.md"
INTERVIEW_PATH = (
    REPO_ROOT / ".claude" / "skills" / "requirements-interview" / "SKILL.md"
)
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
def interview_text() -> str:
    return INTERVIEW_PATH.read_text(encoding="utf-8")


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


@pytest.fixture(scope="module")
def step_2_region(spec_text: str) -> str:
    """Return the substring covering Step 2 of /spec."""
    start = spec_text.find("2. **Run the adversarial requirements interview**")
    assert start != -1, "Step 2 anchor not found in spec.md"
    end = spec_text.find("\n3. ", start)
    assert end != -1, "Step 2 has no terminator (`\\n3. `)"
    return spec_text[start:end]


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
    assert "Problem, User stories, Ontology, Data model" in step_6_region, (
        "Step 6 must pass the PRD Ontology section to spec-generator"
    )
    assert ".agents/specs/ontology/" in step_6_region, (
        "Step 6 must name the OntologyFragment path passed to spec-generator"
    )


def test_ontology_fragment_carried_into_step_2(step_2_region: str) -> None:
    """Step 2 receives the fragment before the PRD is written."""
    assert "OntologyFragment from Step 1" in step_2_region, (
        "Step 2 must pass the OntologyFragment into requirements-interview"
    )
    assert "output PRD includes an `## Ontology` section" in step_2_region, (
        "Step 2 must require the PRD to carry the ontology section forward"
    )


def test_requirements_interview_outputs_ontology_section(
    interview_text: str,
) -> None:
    """The interview PRD carries ontology forward before Step 6."""
    assert "`Ontology`" in interview_text, (
        "requirements-interview structured output must include Ontology"
    )
    assert "caller-provided OntologyFragment" in interview_text, (
        "requirements-interview must summarize the provided OntologyFragment"
    )
    assert "Optional: OntologyFragment from `/spec` Step 1" in interview_text, (
        "requirements-interview inputs must accept the Step 1 OntologyFragment"
    )
    assert "Read the OntologyFragment if provided" in interview_text, (
        "requirements-interview process must read the fragment before elicitation"
    )
    assert "2. **Ontology.**" in interview_text, (
        "requirements-interview branch checklist must include ontology"
    )


def test_ontology_checks_reference_real_spec_artifact_paths(
    spec_text: str,
    completeness_text: str,
) -> None:
    """Ontology coverage points at generated REQ and DESIGN artifacts."""
    assert ".agents/specs/requirements/REQ-NNN-{slug}.md" in spec_text, (
        "Step 1 ontology handoff must name the generated REQ artifact pattern"
    )
    assert "`requirements.md`" not in spec_text, (
        "Step 1 ontology handoff must not point at a non-emitted requirements.md"
    )
    assert ".agents/specs/design/DESIGN-NNN-{slug}.md" in completeness_text, (
        "completeness prompt must name the generated DESIGN artifact pattern"
    )
    assert "`design.md`" not in completeness_text, (
        "completeness prompt must not point at a non-emitted design.md"
    )


def test_ontology_coverage_not_mislabeled_as_step_7(spec_text: str) -> None:
    """The ontology coverage gate lives in CI, not /spec Step 7."""
    assert "Step 7 completeness" not in spec_text, (
        "ontology completeness must not be mislabeled as /spec Step 7"
    )
    assert "Step 7 ontology" not in spec_text, (
        "ontology coverage must not be mislabeled as /spec Step 7"
    )
    assert "CI completeness check" in spec_text, (
        "ontology coverage handoff must name the CI completeness check"
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
    assert "ask the caller/user to extend the ontologyfragment" in lowered, (
        "spec-generator must give non-/spec callers an actionable repair path"
    )


def test_generator_design_traces_decision_rules_to_o5(
    generator_text: str,
) -> None:
    """Design artifacts map domain decision rules to O5 ontology sources."""
    lowered = generator_text.lower()
    assert "decision-rule traceability" in lowered, (
        "spec-generator must render design decision-rule traceability"
    )
    assert "ontologyfragment `## o5` source" in lowered, (
        "design rule traceability must cite OntologyFragment O5 sources"
    )
    assert "`2` configuration or file-read error" in lowered, (
        "spec-generator must document validator exit code 2"
    )
    assert ".claude/skills/spec-generator/scripts/validate_spec_frontmatter.py" in lowered, (
        "spec-generator must cite the validator path that exists in the repo"
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
    it MUST NOT introduce a new top-level token without a CI allowlist change."""
    # ONTOLOGY-INCOMPLETE would need a coordinated action allowlist update. This
    # prompt keeps ontology coverage inside its existing domain verdicts.
    assert not re.search(r"VERDICT:\s*ONTOLOGY", completeness_text), (
        "completeness check must not emit a new ONTOLOGY-* verdict token"
    )
    # The prompt still emits the three domain verdicts it owns.
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


def test_completeness_check_treats_fragment_as_canonical_source(
    completeness_text: str,
) -> None:
    """When the fragment exists, REQ-local ontology text cannot mint entities."""
    lowered = completeness_text.lower()
    normalized = " ".join(lowered.split())
    assert "every domain entity" in lowered and "ontologyfragment" in lowered, (
        "completeness check must require entity coverage in the OntologyFragment"
    )
    assert "cannot introduce an entity absent from the fragment" in normalized, (
        "REQ-local `## Ontology` sections must not mask fragment drift"
    )
    assert "run entity coverage and decision-rule traceability only when an ontologyfragment exists" in normalized, (
        "ontology checks must not fail degraded runs that lack a fragment"
    )
    assert "referenced anywhere in generated spec artifacts" in normalized, (
        "entity coverage must apply to all generated spec artifacts"
    )


def test_step_9_prior_art_check_independent_of_ontology(spec_text: str) -> None:
    """Check 9d remains focused on Prior Art even when ontology text is present."""
    start = spec_text.find("**Check 9d, Prior Art / Constraints elicitation**")
    assert start != -1, "Check 9d heading not found"
    region = spec_text[start : start + 1200].lower()
    assert "evaluate 9d independently from ontology checks" in region, (
        "Check 9d must state ontology coverage cannot affect prior-art verdicts"
    )
    assert "## prior art / constraints" in region, (
        "Check 9d must keep the literal Prior Art / Constraints section salient"
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


def test_empty_entity_vacuous_coverage_requires_no_requirement_entities(
    completeness_text: str,
) -> None:
    """Empty ontology coverage is vacuous only when REQs name no entities."""
    lowered = " ".join(completeness_text.lower().split())
    assert "requirements also reference no domain entities" in lowered, (
        "empty-entity ontology must require generated requirements name no entities"
    )
    assert "critical entity-coverage gap" in lowered, (
        "requirements naming entities against O1=none must fail closed"
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


def test_reference_fragment_empty_entity_rule_matches_fail_closed_prompt() -> None:
    """The reference ontology records the same empty-entity guard as CI."""
    text = " ".join(REFERENCE_FRAGMENT.read_text(encoding="utf-8").lower().split())
    assert "only when generated requirements reference zero domain entities" in text, (
        "reference fragment must not allow O1=none to mask requirement entities"
    )
    assert "ci completeness check" in text, (
        "reference fragment must name the CI completeness check, not /spec Step 7"
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
