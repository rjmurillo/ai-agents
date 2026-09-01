"""The completeness prompt's Non-Executable Criteria rules (issue #5366).

The fix for #5366 has two halves and the prompt is the load-bearing one. The
classifier in `scripts/ci/spec_nonexecutable_criteria.py` is deliberately narrow
and names only the criteria it can recognize; every criterion it misses falls
through to this prompt section. Delete the section and the classifier suite and
the context suite both stay green, because neither reads the prompt, while the
reviewer loses the only instruction that says what to do with a criterion it
cannot execute.

That is the gap this file closes. It pins the rules a reviewer's behavior
depends on, not the prose around them.

Scoped to the section body rather than the whole file. A phrase asserted against
the file as a whole survives the section's deletion whenever the same words
appear in a neighbouring section, which is the same failure
`.claude/rules/testing.md` MUST-9 describes for substring assertions on
structured files. `test_the_section_scope_is_real` is the control for that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = _REPO_ROOT / ".github" / "prompts" / "spec-check-completeness.md"

_SECTION_TITLE = "Non-Executable Criteria"


def _section_body(title: str) -> str:
    """Return the lines under the `## <title>` heading, up to the next `## `.

    Reading the section rather than the file is what makes a deletion fail:
    the surrounding document keeps discussing `N/A` and `PARTIAL` for the
    Incremental Scope rules, so a file-wide search would still find them.
    """
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
    body = _section_body(_SECTION_TITLE)
    assert body.strip(), (
        f"The '## {_SECTION_TITLE}' section is missing from {_PROMPT.name}. "
        "The classifier is deliberately narrow and every criterion it does not "
        "name falls through to this section, so without it the reviewer has no "
        "instruction for a criterion it cannot execute and the gate returns to "
        "failing closed (issue #5366). Every assertion below would pass "
        "vacuously on an empty body."
    )
    return body


class TestTheExemptionRuleSurvives:
    def test_run_evidence_is_marked_not_applicable(self, section: str) -> None:
        assert "N/A" in section
        assert "historical-run-evidence" in section or "historical run evidence" in section

    def test_partially_satisfied_is_forbidden_for_run_evidence(self, section: str) -> None:
        """The verdict token swap is the whole fix.

        `PARTIAL` is a failure token in `scripts/ai_review_common/verdict.py`,
        so a reviewer that reaches for `PARTIALLY SATISFIED` here fails the
        gate closed on every re-run.
        """
        assert "never `PARTIALLY SATISFIED`" in section

    def test_partial_and_fail_are_forbidden_for_an_unrunnable_claim(self, section: str) -> None:
        assert "Do NOT emit `PARTIAL` or `FAIL`" in section

    def test_na_criteria_are_excluded_from_the_completeness_score(self, section: str) -> None:
        assert "Evaluate completeness only over the non-N/A criteria" in section


class TestTheScopeLimitSurvives:
    """The exemption must not swallow contracts the diff can establish."""

    def test_behavioral_contracts_stay_in_scope(self, section: str) -> None:
        """Pinned as the whole clause, not as the phrase "stays in scope".

        The looser assertion passed against a mutant that rewrote this
        sentence to "is also exempt", because "stays in scope" survives in the
        section's closing paragraph. The clause is the contract; the phrase is
        a word that happens to appear twice.
        """
        assert "A **behavioral contract** stays in scope" in section

    @pytest.mark.parametrize(
        "shape",
        ["exit code", "output shape", "error handling"],
    )
    def test_each_in_scope_shape_is_named(self, section: str, shape: str) -> None:
        """Naming the shapes is what stops the exemption widening back.

        A reviewer told only "keep contracts in scope" has no test to apply;
        these are the three the review round found being waved through.
        """
        assert shape in section.lower(), (
            f"The section no longer names {shape!r} as staying in scope. "
            "Required CLI behavior the diff establishes would be marked N/A "
            "and measured by nothing."
        )

    def test_ambiguity_resolves_toward_keeping_the_criterion(self, section: str) -> None:
        assert "keep the criterion in scope" in section

    def test_the_declaration_is_a_hint_not_an_override(self, section: str) -> None:
        """The deterministic list must not be able to overrule the reviewer.

        The classifier can still name a criterion that reads as a contract on
        changed code; rule 4 is what lets the reviewer keep it.
        """
        assert "unless it reads as a behavioral contract" in section


class TestTheSectionScopeIsReal:
    def test_the_section_scope_is_real(self) -> None:
        """Control: the body really is scoped to one section.

        `## Incremental Scope` is the neighbouring section and also talks about
        `N/A` and completeness. If `_section_body` leaked into it, every
        assertion above would keep passing after the Non-Executable section was
        deleted, which is exactly the false green this file exists to prevent.
        """
        body = _section_body(_SECTION_TITLE)

        assert "Incremental Scope Declaration" not in body
        assert "explicitly delivers only a named slice" not in body

    def test_the_neighbouring_section_is_still_reachable(self) -> None:
        """Control on the control: the extractor finds other sections too.

        Without this, a `_section_body` that returned nothing for every title
        would satisfy the assertions above.
        """
        incremental = _section_body("Incremental Scope")

        assert "Incremental Scope Declaration" in incremental
