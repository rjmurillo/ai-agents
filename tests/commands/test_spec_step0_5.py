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
and parser logic without an LLM in the loop. The LLM-required subset
(D1, D6, D7, D9, D12, D13, D14) is promoted to ADR-057 behavioral
scenarios in `tests/evals/spec-scenarios.json`. The remaining D3-D5
manual checks require live tool-invocation trace assertions that are
outside issue #1972.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.commands.step0_5_parser import (
    GUARD_STRING,
    HALT_BLOCK_FIELDS,
    STEP_0_5_HEADING,
    VALID_HALT_TRIGGERS,
    adjudicate_entity_scope,
    compute_provisional_tier,
    entity_matches_answer,
    extract_step0_5_block,
    extract_step0_5_subsection,
    extract_step9_block,
    has_guard_string,
    load_entity_aliases,
    normalize_topic,
    normalize_topic_with_aliases,
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
    # Issue #1973 changed how case-insensitivity is documented: it is now
    # stated as a consequence of normalization rule 2 (lowercase) rather
    # than as a separate "case-insensitive substring match" clause. The
    # rule still documents case handling, so assert on the new wording.
    assert "Case-insensitivity is already handled" in body
    assert "auto-mode" in body or "Auto" in body


def test_s8_auto_mode_uses_whole_token_equality_not_substring(spec_text: str):
    """Issue #1973: the auto-mode adjudication rule must specify whole-token
    equality, not substring match (REQ-008 Sec F2, CWE-863).

    The fix replaces the substring rule that let a token-rich Q1 trivially
    "match" any short discovered entity, hiding genuine blast-radius
    entities from the halt threshold. The rule text and the Auto threshold
    row both name the whole-token mechanism so the LLM enforces it at
    runtime.
    """
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 entity adjudication",
    )
    assert "whole-token equality" in body, (
        "auto-mode rule must specify whole-token equality"
    )
    assert "not substring match" in body, (
        "rule must explicitly reject substring matching"
    )
    assert "Auto (whole-token equality only)" in body, (
        "blast-radius threshold table must name whole-token matching for Auto"
    )
    assert "CWE-863" in body, (
        "rule should cite the access-control weakness it closes"
    )


def test_s8_auto_mode_adjudication_applies_rule_5_aliases(spec_text: str):
    """Auto-mode prose matches parser behavior for entity alias spans."""
    body = extract_step0_5_subsection(
        spec_text,
        "#### Step 0.5 entity adjudication",
    )
    assert "applies topic normalization rules 1-5 to the discovered entity" in body
    assert "every contiguous token span after applying rule 5 alias lookup" in body
    assert "single-token alias such as `spec`" in body


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
# LLM in the loop. ADR-057 behavioral scenarios for the LLM-required
# #1972 subset live in tests/evals/spec-scenarios.json:
# D1, D6, D7, D9, D12, D13, D14. D3-D5 still require live tool-call
# trace assertions and remain manual.
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

    # PR #2029 (fix/issue-1972-spec-d-evals) supersedes PR #2028 verdict vocabulary.
    # PR #2028 used coarse PASS/FAIL options; PR #2029 uses precise per-check enums
    # that match the actual D-check behaviors defined in ADR-057 and issue #1972.
    # D1 AC-01: Step 0.5 must run (RUN_STEP_0_5, not a generic PASS).
    assert by_id["D1"]["expected_verdict"] == "RUN_STEP_0_5"
    # D6 AC-07: Forgetful failure degrades gracefully (DEGRADED_PASS, not generic PASS).
    assert by_id["D6"]["expected_verdict"] == "DEGRADED_PASS"
    # D7 AC-08: Discovered entity needs adjudication (REQUEST_ADJUDICATION, not PASS).
    assert by_id["D7"]["expected_verdict"] == "REQUEST_ADJUDICATION"
    # D9 AC-09: Under blast-radius threshold, Step 0.5 proceeds (PROCEED_STEP_1, not PASS).
    assert by_id["D9"]["expected_verdict"] == "PROCEED_STEP_1"
    # D12 AC-12: 9d passes on populated PriorArtBlock (PASS, unchanged).
    assert by_id["D12"]["expected_verdict"] == "PASS"
    # D13 AC-12: 9d fails when PriorArtBlock removed (FAIL, unchanged).
    assert by_id["D13"]["expected_verdict"] == "FAIL"
    # D14 AC-10: Tier upgrade triggers supplemental phase (RUN_SUPPLEMENTAL, not PASS).
    assert by_id["D14"]["expected_verdict"] == "RUN_SUPPLEMENTAL"


# ---------------------------------------------------------------------------
# Whole-token equality matcher (Issue #1973, REQ-008 Sec F2, CWE-863)
#
# The parser implements the auto-mode adjudication rule from
# `#### Step 0.5 entity adjudication` deterministically so the substring
# bypass is pinned by a behavioral test, not only by prose. The runtime
# gate is still enforced by the LLM following spec.md; these tests pin the
# same semantics at CI time.
# ---------------------------------------------------------------------------


TOKEN_RICH_ANSWER = "auth-service payment-service billing-service"


def test_normalize_topic_collapses_separators_to_hyphen():
    """Normalization rule 4: whitespace, `-`, `_` runs collapse to one hyphen."""
    assert normalize_topic("spec pipeline") == "spec-pipeline"
    assert normalize_topic("spec-pipeline") == "spec-pipeline"
    assert normalize_topic("spec_pipeline") == "spec-pipeline"
    assert normalize_topic("spec   __  pipeline") == "spec-pipeline"


def test_normalize_topic_strips_leading_dots_and_separators_and_lowercases():
    """Rules 1-3: trim; strip leading `/`, `\\`, `.`; lowercase."""
    assert normalize_topic(".claude/commands/spec.md") == "claude/commands/spec.md"
    assert normalize_topic("  AUTH-Service  ") == "auth-service"
    assert normalize_topic("///leading") == "leading"
    # Regression: leading whitespace must not defeat leading-dot stripping.
    # Rule 1 (trim) runs before rule 2 (strip), so surrounding whitespace is
    # removed before the leading-dot regex applies.
    assert (
        normalize_topic("  .claude/commands/spec.md  ")
        == "claude/commands/spec.md"
    )


def test_normalize_topic_empty_and_separator_only_yield_empty_string():
    assert normalize_topic("") == ""
    assert normalize_topic("   ") == ""
    assert normalize_topic("---") == ""
    assert normalize_topic("__ -- __") == ""


def test_entity_substring_false_match_no_longer_matches():
    """Issue #1973 core case: `service-mesh` must NOT match a token-rich answer.

    Under the old substring rule, `service-mesh` (or any name sharing the
    `service` token) matched `auth-service payment-service billing-service`
    trivially. Whole-token equality rejects it: the token pair
    `service mesh` never appears as a contiguous run in the answer.
    """
    assert entity_matches_answer("service-mesh", TOKEN_RICH_ANSWER) is False
    assert adjudicate_entity_scope("service-mesh", [TOKEN_RICH_ANSWER]) == "blast-radius"


def test_entity_genuine_whole_token_match_still_matches():
    """A genuine entity whose tokens form a contiguous run still resolves in-scope."""
    assert entity_matches_answer("auth-service", TOKEN_RICH_ANSWER) is True
    assert entity_matches_answer("payment-service", TOKEN_RICH_ANSWER) is True
    assert entity_matches_answer("billing-service", TOKEN_RICH_ANSWER) is True
    assert adjudicate_entity_scope("auth-service", [TOKEN_RICH_ANSWER]) == "in-scope"


def test_entity_single_token_matches_standalone_token_only():
    """A lone token matches a standalone token; an unrelated lone token does not."""
    assert entity_matches_answer("service", TOKEN_RICH_ANSWER) is True
    assert entity_matches_answer("mesh", TOKEN_RICH_ANSWER) is False


def test_entity_match_at_answer_start_and_end():
    """Contiguous run is found whether it sits at the head, middle, or tail."""
    assert entity_matches_answer("auth-service", "auth service then more") is True
    assert entity_matches_answer("more-thing", "lead then more thing") is True
    assert entity_matches_answer("payment-service", "auth service payment service") is True


def test_entity_match_is_case_insensitive_via_normalization():
    """Rule 2 (lowercase) makes the match case-insensitive without a separate fold."""
    assert entity_matches_answer("AUTH-SERVICE", TOKEN_RICH_ANSWER) is True
    assert entity_matches_answer("Auth_Service", TOKEN_RICH_ANSWER) is True


def test_entity_match_treats_underscore_and_space_like_hyphen():
    """Rule 4 unifies `_`, space, and `-`, so all three spellings match."""
    assert entity_matches_answer("auth_service", TOKEN_RICH_ANSWER) is True
    assert entity_matches_answer("auth service", TOKEN_RICH_ANSWER) is True


def test_entity_trailing_punctuation_in_answer_does_not_match():
    """Spec normalization strips only LEADING dots/separators, not trailing
    punctuation; `auth-service.` is therefore a distinct token from
    `auth-service`. This pins the documented limitation rather than assuming
    punctuation stripping the spec does not perform.
    """
    assert normalize_topic("auth-service.") == "auth-service."
    assert entity_matches_answer("auth-service", "use auth-service.") is False


def test_entity_empty_inputs_never_match():
    assert entity_matches_answer("", TOKEN_RICH_ANSWER) is False
    assert entity_matches_answer("   ", TOKEN_RICH_ANSWER) is False
    assert entity_matches_answer("auth-service", "") is False


def test_adjudicate_matches_against_any_answer_in_the_list():
    """A whole-token match against ANY Q answer resolves the entity in-scope."""
    answers = ["unrelated topic", "auth service module", "another"]
    assert adjudicate_entity_scope("auth-service", answers) == "in-scope"
    assert adjudicate_entity_scope("service-mesh", answers) == "blast-radius"


def test_entity_adjudication_applies_aliases_to_entity_and_answer_spans():
    """Rule 5 aliases apply before whole-token adjudication."""
    assert entity_matches_answer("spec-pipeline", "the spec command") is True
    assert entity_matches_answer("spec", "the spec pipeline") is True
    assert adjudicate_entity_scope("spec-pipeline", ["the spec command"]) == "in-scope"


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


# ---------------------------------------------------------------------------
# Adversarial delimiter hardening (Issue #1976)
#
# The Step 0.5 block extractor used to terminate on the first literal
# `\n---\n`. A horizontal rule inserted inside a fenced example would truncate
# the block early; a rephrased Step 9 opener would break the Step 9 extractor.
# These tests pin the hardened behavior with synthetic specs so they stay valid
# as the real spec.md prose churns.
# ---------------------------------------------------------------------------


def _synthetic_spec(step0_5_body: str) -> str:
    """Wrap a Step 0.5 body in a minimal spec.md skeleton for parser tests."""
    return (
        "### Step 0: First Principles Gate\n\n"
        "Preamble.\n\n"
        f"{STEP_0_5_HEADING}\n\n"
        f"{step0_5_body}\n"
        "---\n\n"
        "1. Clarify the problem. Step 1 body.\n"
    )


def test_step0_5_block_ignores_horizontal_rule_inside_fenced_example():
    """A `---` inside a fenced code block does not terminate the Step 0.5 block.

    Prose churn that adds a horizontal-rule line inside the PriorArtBlock schema
    example must not truncate the extracted block before its real boundary.
    """
    body = (
        "Some prose before the example.\n\n"
        "```markdown\n"
        "## Prior Art / Constraints\n"
        "\n"
        "---\n"
        "\n"
        "### Direct prior art from memory\n"
        "```\n\n"
        "Trailing prose that MUST appear in the extracted block."
    )
    block = extract_step0_5_block(_synthetic_spec(body))
    assert "Trailing prose that MUST appear in the extracted block." in block
    assert "### Direct prior art from memory" in block
    # The Step 1 body lives past the closing `---` and must NOT be captured.
    assert "Clarify the problem" not in block


def test_step0_5_block_terminates_on_bare_horizontal_rule_outside_fence():
    """A bare `---` line outside any fence closes the block (legacy behavior)."""
    body = "Body line one.\nBody line two."
    block = extract_step0_5_block(_synthetic_spec(body))
    assert "Body line two." in block
    assert "Clarify the problem" not in block


def test_step0_5_block_terminates_on_sibling_h3_before_any_rule():
    """A sibling h3 outside a fence closes the block even with no `---` first.

    The hardened extractor anchors on the next sibling boundary, so a sibling
    h3 that appears before the closing rule terminates the block instead of
    over-running to a later `---`.
    """
    spec = (
        "### Step 0: First Principles Gate\n\n"
        f"{STEP_0_5_HEADING}\n\n"
        "Step 0.5 body content.\n\n"
        "### Some Sibling Section\n\n"
        "Sibling content that is NOT part of Step 0.5.\n"
        "---\n"
    )
    block = extract_step0_5_block(spec)
    assert "Step 0.5 body content." in block
    assert "Some Sibling Section" not in block
    assert "Sibling content" not in block


def test_step0_5_block_handles_four_backtick_outer_fence():
    """A four-backtick outer fence stays open across an inner three-backtick run.

    CommonMark: a closing fence uses the same character and at least as many of
    them as the opening fence. A `---` between the inner ``` lines must not close
    the block.
    """
    body = (
        "````markdown\n"
        "Example halt block:\n"
        "```step0_5-halt\n"
        "trigger: H6\n"
        "```\n"
        "---\n"
        "More fenced content.\n"
        "````\n\n"
        "Real trailing body."
    )
    block = extract_step0_5_block(_synthetic_spec(body))
    assert "Real trailing body." in block
    assert "Clarify the problem" not in block


def test_step0_5_block_missing_heading_raises():
    """Absent Step 0.5 heading raises ValueError, not a silent empty block."""
    with pytest.raises(ValueError, match="Step 0.5 heading not found"):
        extract_step0_5_block("### Step 0: only\n\nNo gate here.\n")


def test_extract_step9_block_matches_rephrased_opener():
    """Step 9 extraction anchors on `9. ` (any opener), not the critic wording.

    A rephrased Step 9 first sentence must not break extraction.
    """
    spec = (
        "8. Prior step.\n"
        "9. Skeptical reviewer pass. Rephrased opener with no critic Task call. "
        "Checks 9a through 9d follow.\n"
        "   - Check 9d: Prior Art / Constraints elicitation.\n"
        "## Evaluation Axes\n"
        "Axes body.\n"
    )
    block = extract_step9_block(spec)
    assert block.startswith("9. Skeptical reviewer pass.")
    assert "Check 9d" in block
    assert "Evaluation Axes" not in block


def test_extract_step9_block_still_matches_canonical_critic_opener():
    """The relaxed anchor still matches the canonical Task(critic) opener."""
    spec = (
        '9. Task(subagent_type="critic"): skeptical review. 9a-9d follow.\n'
        "## Evaluation Axes\n"
    )
    block = extract_step9_block(spec)
    assert block.startswith('9. Task(subagent_type="critic")')
    assert "Evaluation Axes" not in block


def test_extract_step9_block_missing_raises():
    """Absent Step 9 block raises ValueError."""
    with pytest.raises(ValueError, match="Step 9 block not found"):
        extract_step9_block("8. only step.\n## Evaluation Axes\n")


# ---------------------------------------------------------------------------
# PriorArtBlock heading parenthetical contract (Issue #1977)
#
# The schema section must document that the h2 heading is exactly
# `## Prior Art / Constraints`, any trailing parenthetical is optional, and
# check 9d matches by substring. Static assertion on the extracted block.
# ---------------------------------------------------------------------------


def test_s12_prior_art_heading_contract_documented(step0_5_block: str):
    """The PriorArtBlock schema states the exact-heading + substring-9d rule."""
    assert "The h2 heading MUST be exactly `## Prior Art / Constraints`" in (
        step0_5_block
    )
    assert "any trailing parenthetical" in step0_5_block
    assert "matches by substring" in step0_5_block


def test_s12_prior_art_heading_contract_present_in_skill_mirror(skill_text: str):
    """The contract sentence is mirrored in the Copilot CLI SKILL.md block.

    The byte-identical parity test covers this implicitly, but a direct
    assertion fails with a clearer message if the mirror drifts.
    """
    skill_block = extract_step0_5_block(skill_text)
    assert "The h2 heading MUST be exactly `## Prior Art / Constraints`" in (
        skill_block
    )


# ---------------------------------------------------------------------------
# Entity-name alias normalization (Issue #1978)
#
# Rule 5 of Step 0.5 topic extraction: after rules 1-4, look the normalized
# string up in .agents/dictionaries/spec-entity-aliases.json and substitute
# the canonical value on a hit.
# ---------------------------------------------------------------------------

ALIAS_TABLE_PATH = (
    PROJECT_ROOT / ".agents" / "dictionaries" / "spec-entity-aliases.json"
)


def test_alias_table_file_exists_and_is_valid_json():
    """The alias dictionary exists and parses as JSON with an aliases object."""
    assert ALIAS_TABLE_PATH.is_file()
    data = json.loads(ALIAS_TABLE_PATH.read_text(encoding="utf-8"))
    assert isinstance(data.get("aliases"), dict)
    assert 5 <= len(data["aliases"]) <= 20


def test_alias_table_keys_are_already_normalized():
    """Every alias key is itself the result of rules 1-4 (idempotent).

    Rule 5 looks up the rule-4 output, so a key that is not already normalized
    could never match and would be dead config.
    """
    aliases = load_entity_aliases()
    for key in aliases:
        assert normalize_topic(key) == key, (
            f"alias key {key!r} is not in normalized form"
        )


def test_alias_table_canonical_values_are_normalized():
    """Every canonical value is also normalized so adjudication is consistent."""
    aliases = load_entity_aliases()
    for value in aliases.values():
        assert normalize_topic(value) == value, (
            f"canonical value {value!r} is not in normalized form"
        )


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("spec", "spec-pipeline"),
        ("SPEC", "spec-pipeline"),
        ("spec command", "spec-pipeline"),
        ("memory skill", "memory"),
        ("memory_search", "memory"),
        ("knowledge graph", "exploring-knowledge-graph"),
    ],
)
def test_normalize_topic_with_aliases_collapses_synonyms(
    raw: str, expected: str
):
    """Known synonyms collapse to one canonical topic after rule 5."""
    assert normalize_topic_with_aliases(raw) == expected


def test_normalize_topic_with_aliases_passes_through_unknown_topics():
    """A topic with no alias entry is returned as its rule-4 normalized form."""
    # `auth service` normalizes to `auth-service`, which is not an alias key.
    assert normalize_topic_with_aliases("auth service") == "auth-service"
    assert normalize_topic_with_aliases(
        ".claude/commands/spec.md"
    ) == "claude/commands/spec.md"


def test_normalize_topic_with_aliases_accepts_injected_table():
    """An injected alias table avoids the file read and is honored verbatim."""
    table = {"foo": "bar"}
    assert normalize_topic_with_aliases("FOO", aliases=table) == "bar"
    assert normalize_topic_with_aliases("baz", aliases=table) == "baz"


def test_load_entity_aliases_missing_file_returns_empty(tmp_path):
    """A missing alias file degrades to an empty table (pass-through)."""
    missing = tmp_path / "absent.json"
    assert load_entity_aliases(missing) == {}


def test_load_entity_aliases_null_aliases_returns_empty(tmp_path):
    """An explicit null aliases key is equivalent to the optional key missing."""
    target = tmp_path / "aliases.json"
    target.write_text('{"aliases": null}', encoding="utf-8")

    assert load_entity_aliases(target) == {}


def test_load_entity_aliases_malformed_json_fails_closed(tmp_path):
    """Malformed alias config raises instead of silently disabling aliases."""
    target = tmp_path / "aliases.json"
    target.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_entity_aliases(target)


def test_load_entity_aliases_rejects_non_object_aliases(tmp_path):
    """Invalid alias shapes raise instead of widening Step 0.5 scope silently."""
    target = tmp_path / "aliases.json"
    target.write_text('{"aliases": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="'aliases' must be an object"):
        load_entity_aliases(target)


def test_spec_md_documents_alias_lookup_step(step0_5_block: str):
    """spec.md normalization block documents rule 5 and the dictionary path."""
    assert ".agents/dictionaries/spec-entity-aliases.json" in step0_5_block
    assert "substitute the canonical value" in step0_5_block
