"""The traceability prompt's Non-Executable Criteria rules (issue #5366).

The declaration reaches two reviewers. Completeness was taught to mark pure run
evidence `N/A`; traceability was told, for one round, to trace every listed
entry. That moved the issue #5366 false failure rather than removing it: run
evidence has no implementation, so tracing it can only produce `NOT_COVERED`,
and `scripts/ai_review_common/verdict.py` blocks on the trace verdict exactly
as it blocks on completeness.

So the prompt needs both halves, and a test that pins only one of them would
let the other regress. Nothing else reads this file, so without this the
section could be deleted whole and every suite would stay green.

Scoped to the section body for the reason
`tests/ci/test_spec_completeness_prompt_contract.py` records: the neighbouring
Incremental Scope section also discusses `N/A` and `NOT_COVERED`, so a
file-wide search still finds those words after the section is gone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = _REPO_ROOT / ".github" / "prompts" / "spec-trace-requirements.md"

_SECTION_TITLE = "Non-Executable Criteria"


def _section_body(title: str) -> str:
    """Return the lines under the `## <title>` heading, up to the next `## `."""
    lines = _PROMPT.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    inside = False

    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = title.lower() in line.lower()
            continue
        if inside:
            body.append(line)

    return "\n".join(body)


@pytest.fixture(scope="module")
def section() -> str:
    body = " ".join(_section_body(_SECTION_TITLE).split())
    assert body.strip(), (
        f"The '## {_SECTION_TITLE}' section is missing from {_PROMPT.name}. "
        "Without it the analyst traces every declared entry, pure run evidence "
        "included, which can only end in NOT_COVERED and re-creates the issue "
        "#5366 false failure on the traceability verdict. Every assertion "
        "below would pass vacuously on an empty body."
    )
    return body


class TestBothHalvesOfTheSplitSurvive:
    def test_a_behavioral_contract_is_still_traced(self, section: str) -> None:
        assert "behavioral contract" in section
        assert "Trace it" in section

    def test_the_named_contract_shapes_are_kept_in_scope(self, section: str) -> None:
        """The same three shapes the completeness prompt names.

        A reviewer told only "trace contracts" has no test to apply.
        """
        for shape in ("exit codes", "output", "error handling"):
            assert shape in section, f"{shape!r} is no longer named as traceable"

    def test_pure_run_evidence_is_left_out_rather_than_not_covered(self, section: str) -> None:
        assert "only run evidence" in section
        assert "leave it out of the coverage matrix rather than recording it `NOT_COVERED`" in (
            section
        )

    def test_the_verdict_is_not_lowered_for_a_skipped_entry(self, section: str) -> None:
        assert "Do NOT lower the verdict because a run-evidence criterion was skipped" in section

    def test_ambiguity_resolves_toward_tracing(self, section: str) -> None:
        """The safe direction here is the opposite of the completeness one.

        Completeness keeps an ambiguous criterion in scope because a wrongly
        exempted one is measured by nothing. Traceability traces an ambiguous
        entry for the same reason, and the prompt says so explicitly so the
        two are not read as contradicting each other.
        """
        assert "When a criterion could be read either way, trace it" in section


class TestTheRulesStandWithoutADeclaration:
    """The rules must not be gated on the classifier having fired.

    The classifier reads only inline code spans, which is deliberate and
    documented. "All tests pass" names its command in prose, so it produces no
    declaration at all. An earlier version of this section opened with "If the
    additional context contains a `## Non-Executable Criteria Declaration`",
    which scoped every rule to declared entries and left that criterion with no
    instruction covering it, reaching `NOT_COVERED` through the trace path.

    Completeness already had this posture: its run-evidence rule applies to any
    such claim, and its declaration rule says the list "is a hint, not an
    override". These assertions hold traceability to the same shape.
    """

    def test_the_rules_apply_with_or_without_a_declaration(self, section: str) -> None:
        assert "whether or not a declaration names it" in section

    def test_the_declaration_is_a_hint_not_a_gate(self, section: str) -> None:
        assert "hint, not an override" in section
        assert "rule 2 still applies to a criterion it does not name" in section

    def test_the_prose_shape_is_named_as_the_reason(self, section: str) -> None:
        """The specific shape that motivated this, so it cannot be re-narrowed.

        Naming "All tests pass" pins the case rather than the principle, which
        is what a later editor tightening the section would otherwise drop.
        """
        assert "All tests pass" in section
        assert "never reaches the declaration" in section


class TestTheSectionScopeIsReal:
    def test_the_body_does_not_leak_into_the_neighbouring_section(self) -> None:
        """Control: `## Incremental Scope` also discusses N/A and NOT_COVERED."""
        body = _section_body(_SECTION_TITLE)

        assert "Incremental Scope Declaration" not in body
        assert "explicitly delivers only a named slice" not in body

    def test_the_extractor_finds_other_sections(self) -> None:
        """Control on the control: an extractor returning nothing always passes."""
        assert "Incremental Scope Declaration" in _section_body("Incremental Scope")
