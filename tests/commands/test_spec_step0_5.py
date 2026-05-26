# taste-lint: ignore file-size
"""Tests for Step 0.5 Memory-First Gate in /spec command.

Refs #1951, REQ-017, DESIGN-017, TASK-017, plan req-008-step-0-5-memory-first-gate.

File-size suppression rationale: this test module is the unit-test home
for all 12 ACs and the 4 parser helpers. Splitting by AC fragments the
test suite without improving cohesion (every test reads the same
spec.md fixture). Sibling test_spec_step0.py is 522 lines under the
same justification.

Verifies the static structure of Step 0.5 instructions in
`.claude/commands/spec.md` against the 12 acceptance criteria. Parser
logic lives in `tests/commands/step0_5_parser.py`; this file holds only
test cases.

Of 14 dynamic D-checks in TASK-017-5, 4 are promoted to pytest here
(D2, D8, D10, D11) because they are deterministic from spec.md prose
and parser logic without an LLM in the loop. The LLM-required checks
D1, D6, D7, D9, D12, D13, and D14 are captured as ADR-057 scenarios in
`tests/evals/spec-scenarios.json`. D3, D4, and D5 remain manual because
they require live memory-query behavior outside this issue's scope.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.commands.step0_5_parser import (
    GUARD_STRING,
    HALT_BLOCK_FIELDS,
    VALID_HALT_TRIGGERS,
    compute_provisional_tier,
    extract_step0_5_block,
    extract_step0_5_subsection,
    extract_step9_block,
    has_guard_string,
    parse_halt_block,
    parse_tally_line,
    phases_needed,
    supplemental_traversal_warranted,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_MD = PROJECT_ROOT / ".claude" / "commands" / "spec.md"
SKILL_MD = PROJECT_ROOT / "src" / "copilot-cli" / "skills" / "spec" / "SKILL.md"
SPEC_SCENARIOS_JSON = PROJECT_ROOT / "tests" / "evals" / "spec-scenarios.json"

CANONICAL_DEFERRAL_TEXT = (
    "Revise Step 0 Q4 to name blast-radius entities or add explicit "
    "out-of-scope entries; then re-run Step 0.5."
)


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step0_5_block(spec_text: str) -> str:
    return extract_step0_5_block(spec_text)


@pytest.fixture(scope="module")
def step9_block(spec_text: str) -> str:
    return extract_step9_block(spec_text)


# ---------------------------------------------------------------------------
# S1: heading order (AC-01)
# ---------------------------------------------------------------------------


def test_s1_heading_order_step_0_then_step_0_5_then_step_1(spec_text: str):
    step0 = spec_text.find("### Step 0: First Principles Gate")
    step0_5 = spec_text.find(
        "### Step 0.5: Memory-First Gate (blocking, runs after Step 0)"
    )
    step1 = re.search(r"^1\. Clarify the problem\.", spec_text, re.MULTILINE)

    assert step0 != -1, "Step 0 heading missing"
    assert step0_5 != -1, "Step 0.5 heading missing"
    assert step1 is not None, "Step 1 numbered-list anchor missing"
    assert step0 < step0_5 < step1.start(), (
        f"Heading order wrong: Step 0={step0}, Step 0.5={step0_5}, "
        f"Step 1={step1.start()}"
    )


# ---------------------------------------------------------------------------
# S2: ProvisionalTier mapping tables (AC-02)
# ---------------------------------------------------------------------------


def test_s2_provisional_tier_subsection_present(step0_5_block: str):
    assert (
        "#### Step 0.5 ProvisionalTier (auto-classified, no user prompt)"
        in step0_5_block
    )


def test_s2_provisional_tier_hours_mapping_strict_less_than(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 ProvisionalTier (auto-classified, no user prompt)",
    )
    assert "2 to less than 8 hours" in body
    assert "8 to less than 40 hours" in body
    assert "40 to less than 160 hours" in body


def test_s2_provisional_tier_max_formula_present(step0_5_block: str):
    assert "max(hours_tier, entity_tier)" in step0_5_block


def test_s2_provisional_tier_default_when_no_hours(step0_5_block: str):
    assert "default `hours_tier = 2`" in step0_5_block


# ---------------------------------------------------------------------------
# S3: chestertons-fence invocation (AC-03)
# ---------------------------------------------------------------------------


def test_s3_chestertons_fence_invocation_with_target_and_change(
    step0_5_block: str,
):
    assert 'Skill(skill="chestertons-fence")' in step0_5_block
    assert "target" in step0_5_block
    assert "change" in step0_5_block
    assert "Q3" in step0_5_block and "Q4" in step0_5_block


# ---------------------------------------------------------------------------
# S4: memory queries (AC-04)
# ---------------------------------------------------------------------------


def test_s4_memory_minimum_three_distinct_queries(step0_5_block: str):
    assert "search_memory.py" in step0_5_block
    assert "3 distinct query variants" in step0_5_block


# ---------------------------------------------------------------------------
# S5: knowledge-graph depth table (AC-05)
# ---------------------------------------------------------------------------


def test_s5_depth_table_per_provisional_tier(step0_5_block: str):
    assert 'Skill(skill="exploring-knowledge-graph")' in step0_5_block
    assert "Phases 1-2 (shallow)" in step0_5_block
    assert "Phases 1-4 (medium)" in step0_5_block
    assert "Phases 1-5 (deep)" in step0_5_block


# ---------------------------------------------------------------------------
# S6: zero-result coverage note rule (AC-06)
# ---------------------------------------------------------------------------


def test_s6_zero_result_coverage_note_rule(step0_5_block: str):
    assert (
        "Memory search returns 0 results for a topic after at minimum 3 distinct queries"
        in step0_5_block
    ) or (
        "after at minimum 3 distinct queries" in step0_5_block
        and "Coverage notes" in step0_5_block
    )


# ---------------------------------------------------------------------------
# S7: degradation rules (AC-07)
# ---------------------------------------------------------------------------


def test_s7_three_degradation_rules_present(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 degradation rules",
    )
    assert "chestertons-fence" in body
    assert "Forgetful MCP unavailable" in body
    assert "exploring-knowledge-graph" in body


# ---------------------------------------------------------------------------
# S8: entity adjudication and threshold (AC-08)
# ---------------------------------------------------------------------------


def test_s8_adjudication_three_categories(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 entity adjudication",
    )
    assert "in-scope" in body
    assert "out-of-scope" in body
    assert "blast-radius" in body


def test_s8_auto_mode_case_insensitive_match_rule(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 entity adjudication",
    )
    assert "case-insensitive" in body
    assert "auto-mode" in body or "Auto" in body


def test_s8_blast_radius_thresholds_2_human_3_auto(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 entity adjudication",
    )
    assert "Human" in body and "2 or more" in body
    assert "Auto" in body and "3 or more" in body


# ---------------------------------------------------------------------------
# S9: halt block format (AC-09)
# ---------------------------------------------------------------------------


def test_s9_step0_5_halt_info_string_with_five_fields(step0_5_block: str):
    assert "step0_5-halt" in step0_5_block
    for field in ("trigger", "check", "evidence", "test_failed", "deferral"):
        assert f"{field}:" in step0_5_block, f"halt field missing: {field}"


def test_s9_h11_trigger_documented(step0_5_block: str):
    assert "H11" in step0_5_block


def test_s9_canonical_deferral_text_present(step0_5_block: str):
    assert CANONICAL_DEFERRAL_TEXT in step0_5_block


# ---------------------------------------------------------------------------
# S10: supplemental Phase 5 trigger formula (AC-10)
# ---------------------------------------------------------------------------


def test_s10_phases_needed_formula_present(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 supplemental traversal hook (cross-step)",
    )
    assert "phases_needed" in body
    assert "actual_tier > provisional_tier" in body
    assert "phases_needed(actual_tier) > phases_needed(provisional_tier)" in body
    # Verify the per-tier phase-count constants match REQ-017 AC-10
    assert "phases_needed(T) = 2  if T <= 2" in body
    assert "phases_needed(T) = 4  if T == 3" in body
    assert "phases_needed(T) = 5  if T >= 4" in body


def test_s10_supplemental_subblock_heading_documented(step0_5_block: str):
    assert "### Supplemental (Phase" in step0_5_block


# ---------------------------------------------------------------------------
# S11: metrics tally (AC-11)
# ---------------------------------------------------------------------------


def test_s11_metrics_file_path_and_format(spec_text: str):
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 metrics tally",
    )
    assert ".agents/sessions/STEP-0.5-METRICS.md" in body
    assert "<YYYY-MM-DDTHH:MM:SSZ> | <pass|fail>" in body
    assert "canonical `YYYY-MM-DDTHH:MM:SSZ`" in body
    assert "100 entries" in body


# ---------------------------------------------------------------------------
# S12: check 9d in Step 9 (AC-12)
# ---------------------------------------------------------------------------


def test_s12_check_9d_in_step_9(step9_block: str):
    assert "Check 9d, Prior Art / Constraints elicitation" in step9_block


def test_s12_check_9d_pass_condition_lists_three_subsections(step9_block: str):
    assert "### Direct prior art from memory" in step9_block
    assert "### Connected context from exploring-knowledge-graph" in step9_block
    assert "### Coverage notes" in step9_block


def test_s12_check_9d_includes_guard_token_fail_clause(step9_block: str):
    """9d FAIL clause must reference the guard token by name without
    embedding the literal HTML-comment marker.

    Rationale: if the literal `<!-- step0.5:incomplete-without-2b -->`
    appeared in the Step 9 prose, a naive whole-file substring check
    would self-trigger 9d. The clause names the token wrapped in
    backticks and qualifies it as `wrapped in HTML-comment delimiters`,
    which 9d's runtime check resolves by extracting the Step 0.5 block
    first and matching the literal only inside that block.
    """
    assert "step0.5:incomplete-without-2b" in step9_block, (
        "9d FAIL clause must name the guard token for runtime detection"
    )
    assert GUARD_STRING not in step9_block, (
        "9d FAIL clause must not embed the literal HTML-comment marker; "
        "it would cause a tautological self-trigger on whole-file checks"
    )


def test_s12_guard_string_absent_from_step_0_5_body(step0_5_block: str):
    """After commit 2B lands, the guard must not appear in the Step 0.5 body.

    The string IS allowed in Step 9 9d's FAIL-clause documentation (it
    names the guard so the check can detect it at runtime). Per-block
    scoping is the correct invariant: 9d MUST match only inside the
    Step 0.5 block, not the whole spec.md, to avoid a tautological
    self-trigger from this Step 9 text.
    """
    assert GUARD_STRING not in step0_5_block, (
        "guard string `<!-- step0.5:incomplete-without-2b -->` must not "
        "appear in Step 0.5 body after commit 2B. It belongs ONLY in "
        "Step 9 9d FAIL clause documentation."
    )


def test_s12_has_guard_string_returns_false_after_2b(spec_text: str):
    """`has_guard_string(text)` returns False after commit 2B lands.

    Step 9 9d documentation references the guard TOKEN NAME (the inner
    string `step0.5:incomplete-without-2b`) but NOT the literal HTML
    comment marker (`<!-- step0.5:incomplete-without-2b -->`). The
    literal HTML comment must be absent from spec.md anywhere after 2B
    to avoid a tautological self-trigger when whole-file substring
    detection runs. Runtime 9d performs Step 0.5 block-scoped detection.
    """
    assert not has_guard_string(spec_text), (
        "literal `<!-- step0.5:incomplete-without-2b -->` must not "
        "appear anywhere in spec.md after 2B (token name without HTML "
        "comment marker is the documented form)"
    )


# ---------------------------------------------------------------------------
# Reference cases for compute_provisional_tier (AC-02)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q4_text, entity_count, expected",
    [
        ("6 hours", 1, 2),
        ("3 days", 5, 3),
        ("vague description with no number", 10, 4),
        ("2 weeks", 2, 4),
    ],
)
def test_compute_provisional_tier_reference_cases(
    q4_text: str, entity_count: int, expected: int
):
    assert compute_provisional_tier(q4_text, entity_count) == expected


def test_compute_provisional_tier_seven_point_nine_hours_is_tier_2():
    """REQ-017 AC-02: <8h is Tier 2 (Tier 2 range is `2 to less than 8`)."""
    assert compute_provisional_tier("7.9 hours", 1) == 2


def test_compute_provisional_tier_eight_hours_is_tier_3():
    """REQ-017 AC-02 boundary: 8h is in Tier 3 (range `8 to less than 40`).

    The Tier 2 range is `2 to less than 8` (strict upper bound), so 8h
    falls in Tier 3, not Tier 2. The mapping table is the canonical
    source; any contradicting parenthetical in prose is a doc bug.
    """
    assert compute_provisional_tier("8 hours", 1) == 3


def test_compute_provisional_tier_no_hours_defaults_to_tier_2():
    assert compute_provisional_tier("", 1) == 2


# Entity-count boundary cases (REQ-017 AC-02 entity_tier mapping)
@pytest.mark.parametrize(
    "entity_count, expected_entity_tier",
    [
        (0, 1),
        (1, 1),
        (2, 2),
        (3, 2),
        (4, 3),
        (7, 3),
        (8, 4),
        (15, 4),
        (16, 5),
        (100, 5),
    ],
)
def test_compute_provisional_tier_entity_count_boundaries(
    entity_count: int, expected_entity_tier: int
):
    """REQ-017 AC-02: 1=T1; 2-3=T2; 4-7=T3; 8-15=T4; >15=T5.

    0 entities maps to Tier 1 (Step 0 Q3 always names at least one
    entity in practice; this is the conservative floor for empty input).
    """
    # Force empty Q4 so result depends only on entity_tier.
    assert compute_provisional_tier("", entity_count) == max(
        2, expected_entity_tier
    )


# AC-10 supplemental Phase 5 behavioral cases
@pytest.mark.parametrize(
    "tier, expected_phases",
    [(1, 2), (2, 2), (3, 4), (4, 5), (5, 5)],
)
def test_phases_needed_per_tier(tier: int, expected_phases: int):
    assert phases_needed(tier) == expected_phases


@pytest.mark.parametrize(
    "provisional, actual, expected",
    [
        (2, 2, False),
        (2, 3, True),
        (2, 4, True),
        (3, 4, True),
        (3, 3, False),
        (4, 5, False),
        (1, 2, False),
        (4, 4, False),
    ],
)
def test_supplemental_traversal_warranted(
    provisional: int, actual: int, expected: bool
):
    """AC-10: supplemental fires when actual tier > provisional AND
    actual tier needs more phases than provisional already ran."""
    assert (
        supplemental_traversal_warranted(provisional, actual) is expected
    )


# ---------------------------------------------------------------------------
# Dynamic-check promotion (TASK-017-5 D-list)
#
# 4 of 14 D-checks (D2, D8, D10, D11) are promoted to pytest because
# they are deterministic from spec.md prose and parser logic without an
# LLM in the loop. D1, D6, D7, D9, D12, D13, and D14 are promoted to
# ADR-057 behavioral scenarios in tests/evals/spec-scenarios.json.
# D3, D4, and D5 remain manual because they require live memory-query
# behavior outside #1972's scope.
# ---------------------------------------------------------------------------


# D2 (AC-02, AC-05): Q4 = "4-6 hours"; entity count = 2.
# Expect ProvisionalTier = 2; depth = Phases 1-2.
def test_d2_q4_4_to_6_hours_with_two_entities_yields_tier_2():
    assert compute_provisional_tier("4-6 hours", 2) == 2


def test_d2_q4_4_to_8_hours_with_two_entities_yields_tier_3():
    """Boundary expansion: 4-8 hours picks 8 (last numeric), so Tier 3."""
    assert compute_provisional_tier("4-8 hours", 2) == 3


# D8 (AC-09 halt): a step0_5-halt block emitted on H11 must have exactly
# 5 fields with valid trigger.
def test_d8_halt_block_parses_with_five_fields():
    sample = (
        "```step0_5-halt\n"
        "trigger: H11\n"
        "check: AC-09 blast-radius adjudication\n"
        "evidence: 3 unmatched entities marked blast-radius (a, b, c)\n"
        "test_failed: blast-radius count >= auto-mode threshold (3)\n"
        "deferral: Revise Step 0 Q4 to name blast-radius entities or "
        "add explicit out-of-scope entries; then re-run Step 0.5.\n"
        "```"
    )
    fields = parse_halt_block(sample)
    assert set(fields) == set(HALT_BLOCK_FIELDS)
    assert fields["trigger"] == "H11"
    assert fields["trigger"] in VALID_HALT_TRIGGERS


def test_d8_halt_block_rejects_unknown_trigger():
    sample = (
        "```step0_5-halt\n"
        "trigger: H99\n"
        "check: AC-09\n"
        "evidence: x\n"
        "test_failed: y\n"
        "deferral: z\n"
        "```"
    )
    with pytest.raises(ValueError, match="not in valid set"):
        parse_halt_block(sample)


def test_d8_halt_block_rejects_missing_field_by_line_count():
    sample = (
        "```step0_5-halt\n"
        "trigger: H11\n"
        "check: AC-09\n"
        "evidence: x\n"
        "test_failed: y\n"
        "```"
    )
    with pytest.raises(ValueError, match="exactly 5"):
        parse_halt_block(sample)


def test_d8_halt_block_rejects_extra_field_by_line_count():
    sample = (
        "```step0_5-halt\n"
        "trigger: H11\n"
        "check: AC-09\n"
        "evidence: x\n"
        "test_failed: y\n"
        "deferral: z\n"
        "extra: w\n"
        "```"
    )
    with pytest.raises(ValueError, match="exactly 5"):
        parse_halt_block(sample)


def test_d8_halt_block_rejects_wrong_field_name():
    """5 lines but field set has wrong name."""
    sample = (
        "```step0_5-halt\n"
        "trigger: H11\n"
        "check: AC-09\n"
        "evidence: x\n"
        "test_failed: y\n"
        "wrong_name: z\n"
        "```"
    )
    with pytest.raises(ValueError, match="field set wrong"):
        parse_halt_block(sample)


def test_d8_halt_block_rejects_missing_fence():
    with pytest.raises(ValueError, match="no fenced"):
        parse_halt_block("trigger: H11\ncheck: AC-09\n")


def test_d8_halt_block_rejects_duplicate_key():
    sample = (
        "```step0_5-halt\n"
        "trigger: H11\n"
        "trigger: H10\n"
        "check: AC-09\n"
        "evidence: x\n"
        "test_failed: y\n"
        "```"
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_halt_block(sample)


def test_d8_halt_block_rejects_non_key_value_line():
    sample = (
        "```step0_5-halt\n"
        "trigger: H11\n"
        "check: AC-09\n"
        "evidence: x\n"
        "this is a free-form prose line\n"
        "deferral: z\n"
        "```"
    )
    with pytest.raises(ValueError, match="`key: value`"):
        parse_halt_block(sample)


# D10 (AC-11 pass): tally line for pass case.
def test_d10_pass_tally_line_parses():
    line = "2026-05-10T04:30:00Z | pass | none | none"
    fields = parse_tally_line(line)
    assert fields["state"] == "pass"
    assert fields["trigger"] == "none"
    assert fields["check"] == "none"


def test_d10_pass_tally_line_rejects_non_none_trigger():
    line = "2026-05-10T04:30:00Z | pass | H11 | none"
    with pytest.raises(ValueError, match="pass-state"):
        parse_tally_line(line)


# D11 (AC-11 halt): tally line for halt case.
def test_d11_halt_tally_line_parses():
    line = "2026-05-10T05:15:00Z | fail | H11 | AC-09 blast-radius adjudication"
    fields = parse_tally_line(line)
    assert fields["state"] == "fail"
    assert fields["trigger"] == "H11"
    assert "AC-09" in fields["check"]


def test_d11_halt_tally_line_rejects_none_trigger():
    line = "2026-05-10T05:15:00Z | fail | none | AC-09"
    with pytest.raises(ValueError, match="fail-state"):
        parse_tally_line(line)


def test_d10_d11_tally_line_rejects_malformed_timestamp():
    line = "2026/05/10 04:30 | pass | none | none"
    with pytest.raises(ValueError, match="canonical format"):
        parse_tally_line(line)


def test_llm_required_d_checks_have_adr057_scenarios():
    """Issue #1972: live /spec D-checks are covered by eval scenarios.

    Asserts uniqueness of scenario IDs BEFORE the dict collapse so a duplicate
    ID is caught here; otherwise eval-suite would report results keyed by a
    collapsed ID and ambiguity would slip through. Per PR #2028 review.
    """
    assert SPEC_SCENARIOS_JSON.exists(), (
        f"Expected scenarios fixture not found at {SPEC_SCENARIOS_JSON}. "
        "tests/evals/spec-scenarios.json is required for ADR-057 D-check "
        "coverage of /spec Step 0.5."
    )
    payload = json.loads(SPEC_SCENARIOS_JSON.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]

    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids)), (
        "spec-scenarios.json must not contain duplicate scenario IDs; "
        "eval results are keyed by scenario_id and duplicates produce "
        f"ambiguous output. Found: {ids}"
    )

    by_id = {scenario["id"]: scenario for scenario in scenarios}
    expected_d_checks = {"D1", "D6", "D7", "D9", "D12", "D13", "D14"}
    assert set(by_id) == expected_d_checks
    assert len(scenarios) == len(expected_d_checks)
    for scenario in scenarios:
        assert scenario["desc"]
        assert scenario["input"]
        assert scenario["expected_verdict"] in scenario["verdict_options"]
        assert scenario["expected_reason_contains"]
        assert scenario["rationale"]
        assert scenario["id"].startswith("D")

    assert by_id["D1"]["expected_verdict"] == "PASS"
    assert by_id["D6"]["expected_verdict"] == "PASS"
    assert by_id["D7"]["expected_verdict"] == "PASS"
    assert by_id["D9"]["expected_verdict"] == "PASS"
    assert by_id["D12"]["expected_verdict"] == "PASS"
    assert by_id["D13"]["expected_verdict"] == "FAIL"
    assert by_id["D14"]["expected_verdict"] == "PASS"


# ---------------------------------------------------------------------------
# Mirror parity: spec.md and Copilot CLI SKILL.md must agree byte-for-byte
# on the Step 0.5 block. Same invariant as test_spec_step0.py for Step 0.
# ---------------------------------------------------------------------------


def test_step0_5_block_byte_identical_across_spec_and_skill(
    spec_text: str, skill_text: str
):
    """The Step 0.5 block must be byte-identical in both files.

    The Copilot CLI twin at src/copilot-cli/skills/spec/SKILL.md mirrors
    .claude/commands/spec.md. Drift between them would silently change
    behavior depending on which entry point a user invoked.
    """
    assert extract_step0_5_block(spec_text) == extract_step0_5_block(
        skill_text
    )
