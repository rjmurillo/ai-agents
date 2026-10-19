"""Contract tests for the map / GPS / hybrid design selection guidance.

Issue #6657: skill authoring needs one decision rule for when judgment stays
with the model and when work moves into programs. The rule lives in the
existing script-integration-framework reference, not in a new skill.

Scope: these tests check that the guidance, its examples, and its generated
mirrors exist and agree. They match phrases in the reference text, so they show
the examples are present, not that an agent routes a request to the right
design. Behavioral routing is not tested here; a rewording that keeps the
meaning needs a matching test edit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_REF = (
    _REPO / ".claude" / "skills" / "skillforge" / "references" / "script-integration-framework.md"
)
_DOF = _REPO / ".claude" / "skills" / "skillforge" / "references" / "degrees-of-freedom.md"
_BOOTSTRAP_REF = (
    _REPO / ".claude" / "skills" / "skill-bootstrap" / "references" / "authoring-and-gates.md"
)
_SKILLFORGE_TMPL = _REPO / "templates" / "skills" / "skillforge.SKILL.md.tmpl"
_MIRROR_ROOTS = (
    "src/claude",
    "src/codex",
    "src/copilot-cli",
    "src/cursor",
    "src/hermes/project-toolkit-knowledge",
)
_MIRRORED = (
    ("skillforge", "references/script-integration-framework.md"),
    ("skillforge", "references/degrees-of-freedom.md"),
    ("skillforge", "references/regression-questions.md"),
    ("skillforge", "references/phase4-synthesis-deep-dive.md"),
    ("skillforge", "references/phase1-analysis-deep-dive.md"),
    ("skillforge", "references/phase2-specification-deep-dive.md"),
    ("skillforge", "references/phase3-generation-deep-dive.md"),
    ("skillforge", "references/script-patterns-catalog.md"),
    ("skillforge", "references/output-structure.md"),
    ("skillforge", "references/overview-and-triggers.md"),
    ("skillforge", "assets/templates/script-template.py"),
    ("skillforge", "assets/templates/skill-spec-template.xml"),
    ("skill-bootstrap", "references/authoring-and-gates.md"),
)


def _section(text: str, heading: str) -> str:
    """Return the body of a level-3 section, up to the next heading of level 3 or higher."""
    match = re.search(rf"^### {re.escape(heading)}\n(.*?)(?=^#{{1,3}} |\Z)", text, re.S | re.M)
    assert match, f"section not found: {heading}"
    return match.group(1)


@pytest.fixture(scope="module")
def design_section() -> str:
    return _section(_REF.read_text(encoding="utf-8"), "Design Selection: Map, GPS, or Hybrid")


@pytest.mark.parametrize("design", ["Map", "GPS", "Hybrid"])
def test_each_design_has_a_definition_row(design_section: str, design: str) -> None:
    assert re.search(rf"^\| \*\*{design}\*\* \|", design_section, re.M)


def test_hybrid_names_all_three_stages(design_section: str) -> None:
    row = re.search(r"^\| \*\*Hybrid\*\* \|.*$", design_section, re.M)
    assert row
    text = row.group(0).lower()
    assert "evidence collection" in text
    assert "agent decision" in text
    assert "validation" in text


def test_forcing_questions_cover_all_five_axes(design_section: str) -> None:
    lowered = design_section.lower()
    for axis in ("ambiguous", "postcondition", "undone", "wrong action cost", "instrument already"):
        assert axis in lowered, axis


def test_routing_examples_route_to_expected_design(design_section: str) -> None:
    rows = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^\| ([^|]+?) \| ([^|]+?) \| [^|]+ \|$", design_section, re.M)
    }
    computable = next(v for k, v in rows.items() if "unresolved review threads" in k)
    tradeoff = next(v for k, v in rows.items() if "two architectures" in k)
    mixed = next(v for k, v in rows.items() if "failing-check logs" in k)
    assert computable.startswith("GPS") and "existing instrument" in computable
    assert tradeoff == "Map"
    assert mixed == "Hybrid"


def test_negative_example_unreviewed_automation(design_section: str) -> None:
    row = next(
        (ln for ln in design_section.splitlines() if "unreviewed deterministic automation" in ln),
        None,
    )
    assert row
    assert "keep a reviewed decision" in row


def test_negative_example_no_new_script_when_tool_exists(design_section: str) -> None:
    row = next(
        (ln for ln in design_section.splitlines() if ln.startswith("| Write a new script")), None
    )
    assert row
    assert "Reuse the tool" in row
    assert "verify the capability gap" in row


def test_executor_success_is_separate_from_verified_postcondition() -> None:
    text = _REF.read_text(encoding="utf-8")
    body = _section(text, "Executor Success Is Not Verified Success")
    assert "execution authority" in body
    assert "verification authority" in body
    assert "Exit code 0 shows the executor finished" in body


def test_self_verification_pattern_no_longer_trusts_exit_code() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert "Claude can trust the script's exit code" not in text
    assert "executor success only" in text


def test_pattern_one_is_a_fast_fail_guard_not_verification_authority() -> None:
    text = _REF.read_text(encoding="utf-8")
    body = re.search(r"^### Pattern 1: Fast-Fail Output Check\n(.*?)(?=^### )", text, re.S | re.M)
    assert body, "Pattern 1 section not found or renamed"
    assert "not verification authority" in body.group(1)
    assert "independent postcondition check still runs" in body.group(1)
    assert "Self-verification - the script checks itself" not in text
    assert 'message="Operation verified"' not in text


def test_decision_tree_and_matrix_do_not_treat_exit_code_as_verification() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert "Autonomous verification (skill verifies itself)" not in text
    assert "independent postcondition check" in text
    row = next(
        (ln for ln in text.splitlines() if ln.startswith('| "Check if all tests pass"')), None
    )
    assert row
    assert "not exit 0 alone" in row
    assert "Verification with clear exit code" not in text


def test_thread_count_example_names_the_real_instrument(design_section: str) -> None:
    assert "get_unresolved_review_threads.py" in design_section
    assert "The github skill already returns it" not in design_section
    text = _REF.read_text(encoding="utf-8")
    assert "Count the unresolved threads on a PR" in text
    assert "Count the open threads on a PR" not in text


def test_thread_count_example_reads_the_instrument_fields_not_a_model_count(
    design_section: str,
) -> None:
    row = next(
        (ln for ln in design_section.splitlines() if "unresolved review threads" in ln), None
    )
    assert row
    assert "`unresolved_count`" in row
    assert "`fetched_pages_complete`" in row
    assert "Count it" not in design_section
    assert "Count it" not in _REF.read_text(encoding="utf-8")


def test_self_verification_doctrine_is_retired_from_unchanged_sections() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert "Self-Verification:**" not in text
    assert "| Human verification | Self-verification |" not in text
    assert "verify its own success" not in text
    assert "How will the skill verify its own success?" not in text
    assert "Fast-Fail and Independent Check:**" in text
    assert "| Human verification | Independent verification |" in text


_SKILLFORGE_REFS = _REPO / ".claude" / "skills" / "skillforge" / "references"
_INSTRUMENT = "get_unresolved_review_threads.py"
_SKILLFORGE_SKILL = _REPO / ".claude" / "skills" / "skillforge" / "SKILL.md"
_SKILLFORGE_TEMPLATE_SCRIPT = (
    _REPO / ".claude" / "skills" / "skillforge" / "assets" / "templates" / "script-template.py"
)
_SKILLFORGE_SPEC_TEMPLATE = (
    _REPO / ".claude" / "skills" / "skillforge" / "assets" / "templates" / "skill-spec-template.xml"
)


@pytest.mark.parametrize(
    "path",
    [
        _REF,
        _SKILLFORGE_REFS / "regression-questions.md",
        _SKILLFORGE_REFS / "phase4-synthesis-deep-dive.md",
        _SKILLFORGE_TMPL,
        _SKILLFORGE_SKILL,
        _SKILLFORGE_REFS / "phase1-analysis-deep-dive.md",
        _SKILLFORGE_REFS / "phase2-specification-deep-dive.md",
        _SKILLFORGE_REFS / "phase3-generation-deep-dive.md",
        _SKILLFORGE_REFS / "script-patterns-catalog.md",
        _SKILLFORGE_REFS / "output-structure.md",
        _SKILLFORGE_REFS / "overview-and-triggers.md",
        _SKILLFORGE_TEMPLATE_SCRIPT,
        _SKILLFORGE_SPEC_TEMPLATE,
    ],
    ids=lambda p: p.name,
)
def test_gates_and_checklists_do_not_score_self_verification(path: Path) -> None:
    """Gates and checklists must not reward self-checking, including XML tag names."""
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"self[-_ ]?verif", text, re.I), path.name


def test_spec_template_asks_fast_fail_and_independent_check() -> None:
    text = _SKILLFORGE_SPEC_TEMPLATE.read_text(encoding="utf-8")
    assert text.count("<fast_fail_and_independent_check>") == 2
    assert text.count("</fast_fail_and_independent_check>") == 2
    assert "Can scripts verify their own success?" not in text
    assert "<self_verifies>" not in text


def test_framework_patterns_use_fast_fail_names() -> None:
    """Pattern 1 and Pattern 2 name the same helper as the script template."""
    text = _REF.read_text(encoding="utf-8")
    assert "Fast-fail check failed: {reason}" in text
    assert "Verification failed" not in text
    assert "verify_result(" not in text
    assert "fast_fail_check(result)" in text


def test_generation_path_teaches_fast_fail_plus_independent_check() -> None:
    phase3 = (_SKILLFORGE_REFS / "phase3-generation-deep-dive.md").read_text(encoding="utf-8")
    assert "Add a fast-fail check, and plan an independent postcondition check" in phase3
    phase1 = (_SKILLFORGE_REFS / "phase1-analysis-deep-dive.md").read_text(encoding="utf-8")
    assert "Can a program check the outcome independently of the executor?" in phase1
    catalog = (_SKILLFORGE_REFS / "script-patterns-catalog.md").read_text(encoding="utf-8")
    assert "### Pattern 9: Fast-Fail Output Check" in catalog
    assert "Operation completed and verified" not in catalog
    assert '"verified": True' not in catalog


def test_script_template_check_is_a_fast_fail_guard() -> None:
    text = _SKILLFORGE_TEMPLATE_SCRIPT.read_text(encoding="utf-8")
    assert "def fast_fail_check(" in text
    assert "def verify_result(" not in text
    assert "This is not verification authority." in text
    assert "--no-fast-fail" in text


_CONDITIONAL = "where the outcome can be checked independently"


@pytest.mark.parametrize(
    "path",
    [
        _REF,
        _SKILLFORGE_REFS / "regression-questions.md",
        _SKILLFORGE_REFS / "phase4-synthesis-deep-dive.md",
        _SKILLFORGE_TMPL,
        _SKILLFORGE_SKILL,
    ],
    ids=lambda p: p.name,
)
def test_independent_check_is_required_only_where_it_can_be_checked(path: Path) -> None:
    """The checklist items must carry the same condition as the Executor Success section."""
    text = " ".join(path.read_text(encoding="utf-8").split())
    assert _CONDITIONAL in text or "where it can be checked independently" in text, path.name


def test_framework_checklist_item_is_conditional() -> None:
    text = _REF.read_text(encoding="utf-8")
    marker = "**Fast-Fail and Independent Check:**"
    item = next((ln for ln in text.splitlines() if marker in ln), "")
    assert _CONDITIONAL in item


def test_framework_principle_does_not_claim_autonomy_without_oversight() -> None:
    """The semgrep skill-excessive-autonomy rule flagged the old wording on this line."""
    text = _REF.read_text(encoding="utf-8")
    principle = next((ln for ln in text.splitlines() if ln.startswith("**Principle:**")), "")
    assert "without human intervention" not in principle
    assert "run unattended for scoped, user-approved operations" in principle


def test_framework_decision_tree_admits_an_existing_instrument() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert "Script or existing instrument required (executor script plus" in text
    assert "→ Script required (executor script" not in text


def test_regression_gate_and_synthesis_rubric_name_the_independent_check() -> None:
    regression = (_SKILLFORGE_REFS / "regression-questions.md").read_text(encoding="utf-8")
    rubric = (_SKILLFORGE_REFS / "phase4-synthesis-deep-dive.md").read_text(encoding="utf-8")
    assert "Fast-Fail and Independent Check: Do scripts fail fast" in regression
    assert "a separate check should confirm the outcome" in regression
    assert "**Fast-Fail and Independent Check**" in rubric
    assert "independently verifiable" in rubric


def test_script_header_marker_admits_the_one_real_script() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert "do not exist in this repository" not in text
    assert _INSTRUMENT in text
    real = _REPO / ".claude" / "skills" / "github" / "scripts" / "pr" / _INSTRUMENT
    assert real.is_file(), "marker names a script that must exist"


def test_pattern_one_sample_is_named_for_a_fast_fail_check() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert "def execute_and_verify" not in text
    assert "def execute_and_check(input_data):" in text
    assert "Execute operation and fail fast on a bad result." in text
    assert "Execute operation and verify the result." not in text


def test_matrix_has_hybrid_and_instrument_rows() -> None:
    text = _REF.read_text(encoding="utf-8")
    assert re.search(r"^\| \"Collect CI evidence.*\| Partial \(hybrid\) \|", text, re.M)
    assert re.search(r"^\| \"Count the unresolved threads.*\| Existing instrument \|", text, re.M)


def test_skillforge_template_requires_choice_only_where_it_matters() -> None:
    text = " ".join(_SKILLFORGE_TMPL.read_text(encoding="utf-8").split())
    assert "Design Selection section of the script integration framework" in text
    assert "only where it changes the workflow" in text
    assert "Reuse an existing tool before adding a script" in text


def test_bootstrap_brief_requires_reuse_before_script() -> None:
    text = " ".join(_BOOTSTRAP_REF.read_text(encoding="utf-8").split())
    assert "Reuse an existing instrument first" in text
    assert "verify the capability gap" in text
    assert "only where it changes the workflow" in text


def test_bootstrap_linked_instrument_satisfies_script_requirement() -> None:
    text = " ".join(_BOOTSTRAP_REF.read_text(encoding="utf-8").split())
    assert "A linked, existing instrument satisfies the script requirement" in text
    assert "The tests requirement applies only to a script you add" in text
    assert "plus tests with a positive" not in text


def test_bootstrap_paragraph_is_wrapped_at_file_width() -> None:
    lines = _BOOTSTRAP_REF.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("**Every computable claim"))
    paragraph = []
    for ln in lines[start:]:
        if not ln.strip():
            break
        paragraph.append(ln)
    assert paragraph
    assert max(len(ln) for ln in paragraph) <= 80, max(paragraph, key=len)


def test_degrees_of_freedom_cross_links_design_selection() -> None:
    text = _DOF.read_text(encoding="utf-8")
    assert "script-integration-framework.md" in text
    assert "Design Selection" in text
    # One cross-link only: the decision table must not be duplicated here.
    assert "**Hybrid**" not in text


def test_no_new_skill_or_router_for_the_philosophy() -> None:
    """Name guard only: it rejects skill directories named for the philosophy.

    It does not detect a router, registry, or framework file under another name.
    """
    skills = {p.name.lower() for p in (_REPO / ".claude" / "skills").iterdir() if p.is_dir()}
    offenders = {
        n for n in skills if re.search(r"map-?gps|gps-?map|hybrid-?design|design-?selection", n)
    }
    assert not offenders


@pytest.mark.parametrize(("skill", "rel"), _MIRRORED)
@pytest.mark.parametrize("root", _MIRROR_ROOTS)
def test_generated_mirrors_match_canonical_source(root: str, skill: str, rel: str) -> None:
    canonical = _REPO / ".claude" / "skills" / skill / rel
    mirror = _REPO / root / "skills" / skill / rel
    assert mirror.is_file(), mirror
    assert mirror.read_bytes() == canonical.read_bytes()


def test_pattern_two_unpacks_the_fast_fail_tuple_before_returning() -> None:
    """fast_fail_check returns (is_valid, message); a bare tuple is always truthy."""
    text = _REF.read_text(encoding="utf-8")
    assert "is_valid, reason = fast_fail_check(result)" in text
    assert "if fast_fail_check(result):" not in text


def test_map_only_branch_does_not_require_a_fast_fail_check() -> None:
    """With no executor script there is nothing to fail fast; keep the reviewed decision."""
    phase1 = (_SKILLFORGE_REFS / "phase1-analysis-deep-dive.md").read_text(encoding="utf-8")
    assert "add a fast-fail check only if an executor script runs" in phase1
    assert "NO → Add a fast-fail check and keep" not in phase1
