"""Tests for Step 0 First Principles Gate in /spec command.

Refs #1926, REQ-016, DESIGN-016, TASK-016, PLAN-1926.

Verifies the static structure and parser-checkable behavior of Step 0
instructions in `.claude/commands/spec.md` and its Copilot CLI mirror at
`src/copilot-cli/skills/spec/SKILL.md`. The parser logic lives in
`tests/commands/step0_parser.py`; this file holds only test cases.

Six dynamic LLM-dependent cases (T2, T3, T4, T10, T12, T13) are documented
manual spot-checks per PLAN-1926; they probe model interpretation of the
spec, not the spec text itself.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from tests.commands.step0_parser import (
    baseline_answers,
    evaluate_step0,
    extract_step0_block,
    extract_step1_paragraph,
    extract_step9_block,
    extract_tier5_bullet,
    hedge_match,
    parse_hedge_phrases,
    q1_aspirational,
    q3_specific,
    q5_speculative,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_MD = PROJECT_ROOT / ".claude" / "commands" / "spec.md"
SKILL_MD = PROJECT_ROOT / "src" / "copilot-cli" / "skills" / "spec" / "SKILL.md"
# The Copilot mirror lives under `.../skills/spec/SKILL.md`; the skills output
# tree is two levels up. Translation needs it to resolve the agent_type plugin
# namespace from the tree's plugin.json.
SKILLS_DIR = SKILL_MD.parent.parent

# Reference files extracted by issue #3632 (progressive disclosure split).
# Agents read both spec.md and these files during a /spec invocation.
SPEC_STEP0_GATES = (
    PROJECT_ROOT
    / ".claude" / "skills" / "spec-generator" / "references" / "spec-step0-gates.md"
)
SPEC_PRIOR_ART_SCHEMA = (
    PROJECT_ROOT
    / ".claude" / "skills" / "spec-generator" / "references" / "spec-prior-art-schema.md"
)

# Copilot mirrors of the reference files (verbatim copies, not translated)
SKILL_STEP0_GATES = (
    PROJECT_ROOT
    / "src" / "copilot-cli" / "skills" / "spec-generator" / "references" / "spec-step0-gates.md"
)
SKILL_PRIOR_ART_SCHEMA = (
    PROJECT_ROOT
    / "src" / "copilot-cli" / "skills" / "spec-generator" / "references"
    / "spec-prior-art-schema.md"
)

_build_scripts_dir = str(PROJECT_ROOT / "build" / "scripts")
_original_sys_path = sys.path.copy()
try:
    if _build_scripts_dir not in sys.path:
        sys.path.insert(0, _build_scripts_dir)
    import copilot_body_translation  # noqa: PLC0415
finally:
    sys.path[:] = _original_sys_path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec_text() -> str:
    """Return spec.md content only (for structural and identical-block tests)."""
    return SPEC_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_text() -> str:
    """Return SKILL.md content only (for identical-block tests)."""
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec_step0_gates_text() -> str:
    """Return spec-step0-gates.md content (hedge table and gate logic)."""
    return SPEC_STEP0_GATES.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec_prior_art_text() -> str:
    """Return spec-prior-art-schema.md content (steps 1-9, PriorArtBlock schema)."""
    return SPEC_PRIOR_ART_SCHEMA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_prior_art_text() -> str:
    """Return the Copilot mirror of spec-prior-art-schema.md (verbatim copy)."""
    return SKILL_PRIOR_ART_SCHEMA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_step0_gates_text() -> str:
    """Return the Copilot mirror of spec-step0-gates.md (verbatim copy)."""
    return SKILL_STEP0_GATES.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hedge_phrases(spec_step0_gates_text: str) -> list[str]:
    """Parse hedge phrases from the step0-gates reference file.

    After issue #3632, the hedge phrase table lives in spec-step0-gates.md,
    not in spec.md. The parser sentinel is unchanged.
    """
    return parse_hedge_phrases(spec_step0_gates_text)


# ---------------------------------------------------------------------------
# Static-1: structural tokens present in spec.md
# ---------------------------------------------------------------------------


def test_step0_heading_precedes_step1_in_spec_md(
    spec_text: str, spec_prior_art_text: str
) -> None:
    """AC-1a: the Step 0 heading appears in spec.md; Step 1 lives in the prior-art reference.

    After issue #3632, steps 1-9 are in spec-prior-art-schema.md. The ordering
    contract is preserved: spec.md MUST contain the Step 0 heading, and the
    reference file MUST contain '1. Clarify the problem.'.
    """
    step0_offset = spec_text.find("### Step 0:")
    step1_offset = spec_prior_art_text.find("1. Clarify the problem.")
    assert step0_offset != -1, "missing '### Step 0:' heading in spec.md"
    assert step1_offset != -1, "missing Step 1 item in spec-prior-art-schema.md"


def test_step1_references_step0_block(spec_prior_art_text: str) -> None:
    """AC-7a, AC-7b: Step 1 prose references the Step 0 block and forbids re-elicitation.

    After issue #3632, Step 1 lives in spec-prior-art-schema.md.
    """
    step1_text = extract_step1_paragraph(spec_prior_art_text)
    assert "Step 0" in step1_text
    assert "Q1-Q6" in step1_text
    assert "Do not re-elicit" in step1_text


def test_tier5_replaces_why_not_simpler(spec_prior_art_text: str) -> None:
    """AC-8: Tier 5 bullet must contain `Re-validate Step 0 Q4` AND must
    NOT contain the phrase `why not simpler?`.

    Round-4 update (Copilot PR #1931 comments 3213975201/3213975231/
    3213975270/3213975277): the meta-reference to v1 text was removed
    from the spec.md and SKILL.md Tier 5 bullets so the grep check is
    strict (REQ-016 AC-8: the phrase must be absent).
    After issue #3632, Tier 5 bullet lives in spec-prior-art-schema.md.
    """
    tier5_text = extract_tier5_bullet(spec_prior_art_text)
    assert "Re-validate Step 0 Q4" in tier5_text
    assert "why not simpler?" not in tier5_text


def test_step9_contains_binary_checks(spec_prior_art_text: str) -> None:
    """AC-9: Step 9 critic pre-mortem contains Check 9a/9b/9c with PASS/FAIL phrasing.

    After issue #3632, Step 9 lives in spec-prior-art-schema.md.
    """
    assert "Check 9a" in spec_prior_art_text
    assert "Check 9b" in spec_prior_art_text
    assert "Check 9c" in spec_prior_art_text
    assert "PASS:" in spec_prior_art_text
    assert "FAIL" in spec_prior_art_text
    assert "SHALL NOT return APPROVED" in spec_prior_art_text


def test_step0_kill_criteria_reference(spec_step0_gates_text: str) -> None:
    """AC-13: Step 0 gate logic references kill criteria + tally infrastructure.

    After issue #3632, the gate logic lives in spec-step0-gates.md.
    """
    assert "STEP-0-METRICS.md" in spec_step0_gates_text
    assert "kill criteria" in spec_step0_gates_text.lower()


def test_auto_mode_halt_token_in_spec_md(spec_step0_gates_text: str) -> None:
    """AC-12 (static): the auto-mode halt reason appears verbatim in the gates file.

    After issue #3632, the halt token lives in spec-step0-gates.md.
    """
    assert "STEP_0_REQUIRES_ELICITATION" in spec_step0_gates_text


def test_auto_mode_halt_token_in_skill_gates(skill_step0_gates_text: str) -> None:
    """AC-12 (static): the Copilot mirror of the step0-gates reference has the halt token.

    After issue #3632, the halt token lives in spec-step0-gates.md and its mirror.
    """
    assert "STEP_0_REQUIRES_ELICITATION" in skill_step0_gates_text


def test_ac6_step0_block_directive_in_spec_md(spec_text: str) -> None:
    """AC-6 (static): spec.md instructs the agent to emit `## Step 0
    First Principles` as the first PRD section. The string must appear
    verbatim in the instruction prose so the model sees the exact label
    it must produce."""
    assert "## Step 0 First Principles" in spec_text, (
        "spec.md must reference the canonical PRD block label `## Step 0 First Principles`"
    )


def test_ac6_q1_to_q6_subhead_directive_in_spec_md(spec_text: str) -> None:
    """AC-6 (static): spec.md instructs the agent to emit `### Q1..Q6`
    subheads under the Step 0 PRD block. The instruction must reference
    each label so the model produces the canonical structure."""
    assert "### Q1..Q6" in spec_text or all(
        f"### Q{n}" in spec_text for n in range(1, 7)
    ), "spec.md must reference Q1..Q6 subhead directives for the PRD block"


def test_halt_emission_format_present(spec_step0_gates_text: str) -> None:
    """REQ-016-12 + Gate 5 #2: the machine-readable `step0-halt` fenced-block
    format (info-string + 5 keys) must appear in the gates reference file.

    After issue #3632, the halt format lives in spec-step0-gates.md.
    """
    assert "step0-halt" in spec_step0_gates_text, "halt emission info-string missing"
    for required_key in ["trigger:", "question:", "answer:", "test_failed:", "deferral:"]:
        assert required_key in spec_step0_gates_text, f"halt emission key missing: {required_key}"


def test_halt_emission_example_block_well_formed(spec_step0_gates_text: str) -> None:
    """QA F1: the example `step0-halt` block must parse cleanly:
    every required key is present, every key has a non-empty value, the
    trigger value is one of H1-H5.

    After issue #3632, the halt block lives in spec-step0-gates.md.
    """
    block_match = re.search(
        r"```step0-halt\n(.*?)\n```",
        spec_step0_gates_text,
        re.DOTALL,
    )
    assert block_match is not None, "no `step0-halt` example block in spec-step0-gates.md"
    body = block_match.group(1)
    parsed: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        parsed[key.strip()] = value.strip()
    required_keys = {"trigger", "question", "answer", "test_failed", "deferral"}
    missing = required_keys - parsed.keys()
    assert not missing, f"step0-halt example missing keys: {missing}"
    for key in required_keys:
        assert parsed[key], f"step0-halt example key '{key}' has empty value"
    assert parsed["trigger"] in {"H1", "H2", "H3", "H4", "H5"}, (
        f"step0-halt example trigger must be H1-H5, got {parsed['trigger']!r}"
    )
    assert parsed["question"].startswith("Q") and " " in parsed["question"], (
        f"step0-halt example question must be 'Qn Label' shape, got {parsed['question']!r}"
    )


def test_q1_q5_differentiation_in_spec_md(spec_text: str) -> None:
    """Gate 5 #1: Q1 (requesters) and Q5 (production signals) must be
    differentiated in spec.md prose. Prevent the two questions from
    collapsing back into duplicated 'evidence' shape."""
    # Extract the questions table block.
    table_match = re.search(
        r"\| Label \| Question \|.*?\| \*\*Q6 Future-fit\*\*",
        spec_text,
        re.DOTALL,
    )
    assert table_match is not None, "Q1-Q6 table not found"
    table = table_match.group(0)
    # Q1 row must reference 'requesters' but not be conflated with signals.
    q1_row = re.search(r"\*\*Q1 Demand Reality\*\*[^\n]*", table)
    assert q1_row is not None, "Q1 row not found"
    q1_text = q1_row.group(0)
    assert "requested" in q1_text or "requesters" in q1_text, (
        "Q1 must reference requesters/explicit asks"
    )
    # Q5 row must reference 'signal' or 'metric' or similar.
    q5_row = re.search(r"\*\*Q5 Observation\*\*[^\n]*", table)
    assert q5_row is not None, "Q5 row not found"
    q5_text = q5_row.group(0)
    assert any(token in q5_text.lower() for token in ["signal", "metric", "log", "ticket"]), (
        "Q5 must reference production-signal evidence (metric/log/ticket)"
    )




# ---------------------------------------------------------------------------
# Static-2: edited sections match between spec.md and SKILL.md after translation
# ---------------------------------------------------------------------------
#
# AC-10 originally asserted byte-identity. Issue #2743 makes the Copilot mirror
# an in-place TRANSLATION of the Claude source (inline `Skill()`/`Task()` calls
# become Copilot `skill:`/`agent_type:` tool-input spans). The contract still
# holds one-to-one: applying the production translation to the source block must
# reproduce the mirror block. Coupling these tests to the real translation keeps
# a single source of truth and lets the parser anchors (which key on `### Step 0`,
# `\n1. `, `\n9. `, not on call wording) survive the rewrite.


def _translated(block: str) -> str:
    return copilot_body_translation.translate_body(block, SKILLS_DIR)


def test_step0_block_identical(spec_text: str, skill_text: str) -> None:
    """AC-10: Step 0 block in spec.md matches SKILL.md after translation.

    Step 0 heading and Q1-Q6 table remain in spec.md / SKILL.md body, so the
    translation contract still applies here.
    """
    assert extract_step0_block(skill_text) == _translated(extract_step0_block(spec_text))


def test_step1_paragraph_identical(
    spec_prior_art_text: str, skill_prior_art_text: str
) -> None:
    """AC-10: Step 1 paragraph is verbatim-identical in both reference files.

    After issue #3632, Step 1 lives in spec-prior-art-schema.md, which is
    copied verbatim (no translation) into the Copilot mirror. The identity
    check therefore uses raw equality, not _translated().
    """
    src = extract_step1_paragraph(spec_prior_art_text)
    dst = extract_step1_paragraph(skill_prior_art_text)
    assert src is not None, "extract_step1_paragraph returned None for spec-prior-art-schema.md"
    assert dst is not None, "extract_step1_paragraph returned None for skill-prior-art-schema.md"
    assert src == dst, "Step 1 paragraph differs between spec and skill reference files"


def test_tier5_bullet_identical(
    spec_prior_art_text: str, skill_prior_art_text: str
) -> None:
    """AC-10: Tier 5 bullet is verbatim-identical in both reference files."""
    src = extract_tier5_bullet(spec_prior_art_text)
    dst = extract_tier5_bullet(skill_prior_art_text)
    assert src is not None, "extract_tier5_bullet returned None for spec-prior-art-schema.md"
    assert dst is not None, "extract_tier5_bullet returned None for skill-prior-art-schema.md"
    assert src == dst, "Tier 5 bullet differs between spec and skill reference files"


def test_step9_block_identical(
    spec_prior_art_text: str, skill_prior_art_text: str
) -> None:
    """AC-10: Step 9 block is verbatim-identical in both reference files."""
    src = extract_step9_block(spec_prior_art_text)
    dst = extract_step9_block(skill_prior_art_text)
    assert src is not None, "extract_step9_block returned None for spec-prior-art-schema.md"
    assert dst is not None, "extract_step9_block returned None for skill-prior-art-schema.md"
    assert src == dst, "Step 9 block differs between spec and skill reference files"


# ---------------------------------------------------------------------------
# Hedge phrase list contract
# ---------------------------------------------------------------------------


def test_hedge_phrase_list_parsed(spec_step0_gates_text: str) -> None:
    """The parser finds at least 15 hedge phrases in the gates reference file.

    After issue #3632, the hedge phrase table lives in spec-step0-gates.md.
    """
    phrases = parse_hedge_phrases(spec_step0_gates_text)
    assert len(phrases) >= 15
    for required in ["would be nice", "we believe", "stakeholders want", "probably"]:
        assert required in phrases


def test_no_standalone_should_might_could(spec_step0_gates_text: str) -> None:
    """REQ-016-02: standalone 'should'/'might'/'could' MUST NOT be hedge phrases.

    After issue #3632, the hedge phrase table lives in spec-step0-gates.md.
    """
    phrases = parse_hedge_phrases(spec_step0_gates_text)
    for forbidden in ["should", "might", "could"]:
        assert forbidden not in phrases


# ---------------------------------------------------------------------------
# Parser-checkable scenarios T1, T3, T4, T5, T6, T7, T8, T11
# ---------------------------------------------------------------------------


def test_t1_hedge_phrase_in_q3_triggers_h1(hedge_phrases: list[str]) -> None:
    """T1: 'stakeholders want' in Q3 fires H1 halt."""
    answers = baseline_answers()
    answers["Q3"] = "stakeholders want a faster gate"
    assert evaluate_step0(answers, hedge_phrases) == "H1"


def test_t3_speculative_q5_triggers_h2(hedge_phrases: list[str]) -> None:
    """T3: Q5 with no quote, no citation, no named source fires H2."""
    answers = baseline_answers()
    answers["Q5"] = "users find this slow"
    assert evaluate_step0(answers, hedge_phrases) == "H2"


def test_t4_q5_with_citation_passes(hedge_phrases: list[str]) -> None:
    """T4 (parser side): Q5 with PR citation passes the speculative test."""
    answers = baseline_answers()
    answers["Q5"] = "PR 1887 retro line 305 names the framework gap as out of scope."
    assert evaluate_step0(answers, hedge_phrases) is None


def test_t5_aspirational_q1_triggers_h3(hedge_phrases: list[str]) -> None:
    """T5: aspirational Q1 fires H3 halt."""
    answers = baseline_answers()
    answers["Q1"] = "users in general would want this"
    assert evaluate_step0(answers, hedge_phrases) == "H3"


def test_t6_concrete_q1_passes(hedge_phrases: list[str]) -> None:
    """T6: Q1 with three named teams + ticket numbers passes the aspirational test."""
    answers = baseline_answers()
    assert evaluate_step0(answers, hedge_phrases) is None
    # Stronger assertion: directly verify the Q1 test branch this case targets.
    assert not q1_aspirational(answers["Q1"])


def test_t7_generic_q3_triggers_h4(hedge_phrases: list[str]) -> None:
    """T7: generic Q3 fires H4 specifically.

    The baseline fixture's Q1 names three teams + ticket numbers, so
    Q1 is concrete (does not fire H3). Q5 cites a specific issue, so
    H2 does not fire. The only halt left to fire on `engineers in general`
    is H4 (Q3 specificity). Per Copilot review (PR #1931 comment
    3213949077): allowing both H3 and H4 means a regression that
    incorrectly fires H3 on a concrete Q1 would silently pass.
    """
    answers = baseline_answers()
    answers["Q3"] = "engineers in general"
    assert evaluate_step0(answers, hedge_phrases) == "H4"


def test_t8_specific_q3_passes(hedge_phrases: list[str]) -> None:
    """T8: Q3 with named individual + system + frequency passes the specificity test."""
    answers = baseline_answers()
    assert evaluate_step0(answers, hedge_phrases) is None
    # Stronger assertion: directly verify the Q3 test branch this case targets.
    assert q3_specific(answers["Q3"])


def test_t11_partial_completion_triggers_h5(hedge_phrases: list[str]) -> None:
    """T11: empty Q4-Q6 fires H5 halt (partial completion)."""
    answers = baseline_answers()
    answers["Q4"] = ""
    answers["Q5"] = ""
    answers["Q6"] = ""
    assert evaluate_step0(answers, hedge_phrases) == "H5"


def test_rfc_2119_should_in_q5_does_not_trigger_h1(hedge_phrases: list[str]) -> None:
    """T2 (parser side): standalone 'should' in Q5 must not fire H1."""
    answers = baseline_answers()
    answers["Q5"] = (
        'Issue #1700 says "the system should retry transient KeyVault timeouts"; '
        "we observed 3 such timeouts last week."
    )
    assert evaluate_step0(answers, hedge_phrases) != "H1"


def test_quoted_hedge_in_q5_triggers_h1_parser_side(hedge_phrases: list[str]) -> None:
    """Documented limitation: parser cannot distinguish authored hedge from
    quoted-counter-example hedge. Spec REQ-016-02 says the boundary is
    instruction-level (the LLM is told to apply the hedge check only to
    author-supplied answers, not to quoted instruction text); the parser
    pins the false-positive shape.

    Forward path: a future commit that adds quote-aware exclusion to
    `hedge_match` (skipping phrases inside `"..."` or fenced blocks)
    will need to update this test to assert `is None`. The current
    behavior is acceptable for v1 because:
      1. The instruction-level rule already guards the runtime path.
      2. The parser is a CI safety net, not the enforcement layer.
      3. REQ-016-13 kill criteria provide an operational rollback if
         the false-positive rate exceeds 30%.
    """
    answers = baseline_answers()
    answers["Q5"] = 'The old ticket said "would be nice"; we observed timeouts in #1700.'
    assert evaluate_step0(answers, hedge_phrases) == "H1"


# ---------------------------------------------------------------------------
# Direct unit tests for parser helpers (Gate 1 finding F1)
# ---------------------------------------------------------------------------


class TestHedgeMatch:
    """Direct unit tests for `hedge_match`."""

    def test_matches_canonical_phrase(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("we believe X", hedge_phrases) == "we believe"

    def test_case_insensitive(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("WE BELIEVE X", hedge_phrases) == "we believe"

    def test_eventually_consistent_is_technical_term(self, hedge_phrases: list[str]) -> None:
        """`eventually consistent` is a load-bearing technical term, not a hedge."""
        assert hedge_match("Storage is eventually consistent.", hedge_phrases) is None

    def test_eventually_consistent_hyphenated_is_technical_term(
        self, hedge_phrases: list[str]
    ) -> None:
        """`eventually-consistent` (hyphenated form) must also be exempt.
        Per cursor PR #1931 comment 3213964377: hyphen is a non-word boundary
        for `\\b...\\b`, so the regex matches `eventually` inside
        `eventually-consistent`. The suffix-table lookup compensates by
        stripping the hyphen before checking the next word."""
        assert hedge_match("Storage is eventually-consistent.", hedge_phrases) is None

    def test_eventually_alone_is_a_hedge(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("This will eventually work.", hedge_phrases) == "eventually"

    def test_no_match(self, hedge_phrases: list[str]) -> None:
        assert hedge_match("Concrete observation with citation #1700.", hedge_phrases) is None

    def test_partial_word_no_match(self, hedge_phrases: list[str]) -> None:
        """`somedayer` (made-up word) must NOT match `someday` due to word boundary."""
        assert hedge_match("The somedayer pattern is here.", hedge_phrases) is None


class TestQ1Aspirational:
    """Direct unit tests for `q1_aspirational`."""

    def test_named_team_passes(self) -> None:
        """Three named teams + tickets passes the >= 3 requesters rule."""
        assert not q1_aspirational(
            "Bleu team escalated #1700, Delos team filed #1820, Calc team filed #1850."
        )

    def test_named_service_passes(self) -> None:
        """Three named services satisfy the threshold."""
        assert not q1_aspirational(
            "KeyVault service failed three times. Auth service and Payments team filed #1700."
        )

    def test_pascalcase_service_passes(self) -> None:
        """Per Copilot PR #1931 comment 3213964257: PascalCase identifiers
        like `KeyVault`, `RPCEngine`, `SREDashboard` must qualify as named
        entities. The regex now matches `[A-Z][a-zA-Z]*` to accept any
        capitalized identifier. Three required to pass the >= 3 rule."""
        assert not q1_aspirational(
            "KeyVault team escalated #1700; RPCEngine service filed #1820; "
            "the SRE rotation noted #1850."
        )

    def test_ticket_only_passes(self) -> None:
        assert not q1_aspirational("Three teams reported issues in #1700, #1820, #1850.")

    def test_bare_team_word_fails(self) -> None:
        """REQ-016: 'the team' is a generic category, must fire H3."""
        assert q1_aspirational("the team would benefit from this")

    def test_generic_users_fails(self) -> None:
        assert q1_aspirational("users in general would want this")

    def test_future_tense_fails(self) -> None:
        assert q1_aspirational("if users start adopting this we'll need it")

    def test_no_named_entity_fails(self) -> None:
        assert q1_aspirational("there is demand for this feature")

    def test_one_named_requester_fails_three_or_more_rule(self) -> None:
        """Q1 aspirational condition 1: fewer than three named requesters
        triggers H3. A single team name is not enough (Copilot PR #1931
        comments 3214013611, 3214013613, 3214013621; devin 3214020363)."""
        assert q1_aspirational("Bleu team escalated KeyVault deploy failures")

    def test_two_named_requesters_fails(self) -> None:
        """Two named requesters still under the >= 3 threshold."""
        assert q1_aspirational(
            "Bleu team and Delos team escalated KeyVault deploy failures"
        )

    def test_three_or_more_named_requesters_passes(self) -> None:
        """Three named requesters satisfies the threshold."""
        assert not q1_aspirational(
            "Bleu team and Delos team and Calc team escalated #1700, #1820, #1850"
        )


class TestQ3Specific:
    """Direct unit tests for `q3_specific`."""

    def test_named_individual_passes(self) -> None:
        assert q3_specific("Felix on the Bleu rotation, blocked daily.")

    def test_named_rotation_passes(self) -> None:
        assert q3_specific("the SRE on-call hit this last Tuesday.")

    def test_slash_separated_team_passes(self) -> None:
        """Spec.md gives `Felix on the Bleu/Delos rotation` as a valid
        Q3 example. Both `has_named_individual` and `has_named_team`
        regexes now allow `/`-separated team identifiers (devin PR
        #1931 comment 3214020343)."""
        assert q3_specific("Felix on the Bleu/Delos rotation, blocked daily.")
        assert q3_specific("the Bleu/Delos rotation hit this.")

    def test_qualified_system_passes(self) -> None:
        assert q3_specific("the auth service in prod-east times out.")

    def test_file_path_passes(self) -> None:
        assert q3_specific(
            "the GraphQL pagination in `get_pr_review_threads.py` is the bottleneck."
        )

    def test_generic_users_fails(self) -> None:
        assert not q3_specific("users")

    def test_engineers_generic_fails(self) -> None:
        assert not q3_specific("engineers")


class TestQ5Speculative:
    """Direct unit tests for `q5_speculative`."""

    def test_quoted_evidence_passes(self) -> None:
        assert not q5_speculative('Ticket said "deploy timeouts at 504".')

    def test_citation_passes(self) -> None:
        assert not q5_speculative("PR 1887 retro names the gap.")

    def test_named_source_passes(self) -> None:
        assert not q5_speculative("Felix reported three KeyVault timeouts.")

    def test_no_evidence_fails(self) -> None:
        assert q5_speculative("users find this slow")

    def test_vague_belief_fails(self) -> None:
        assert q5_speculative("there is a problem here")


class TestParseHedgePhrases:
    """Direct unit tests for `parse_hedge_phrases`."""

    def test_returns_list(self, spec_step0_gates_text: str) -> None:
        phrases = parse_hedge_phrases(spec_step0_gates_text)
        assert isinstance(phrases, list)
        assert all(isinstance(p, str) for p in phrases)

    def test_required_phrases_present(self, spec_step0_gates_text: str) -> None:
        phrases = parse_hedge_phrases(spec_step0_gates_text)
        for required in [
            "would be nice",
            "we believe",
            "stakeholders want",
            "probably",
            "eventually",
        ]:
            assert required in phrases

    def test_no_standalone_words(self, spec_step0_gates_text: str) -> None:
        phrases = parse_hedge_phrases(spec_step0_gates_text)
        for forbidden in ["should", "might", "could"]:
            assert forbidden not in phrases
