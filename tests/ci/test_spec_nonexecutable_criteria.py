"""Tests for scripts/ci/spec_nonexecutable_criteria.py (issue #5366).

The detector's job is to name the acceptance criteria a shell-less reviewer
cannot verify. Two failure directions matter and both are covered here:

- Under-firing leaves the gate failing closed on a command-execution claim,
  which is the bug the issue reports.
- Over-firing silently drops a real criterion from the gate, which is worse,
  because the check would go green while measuring less than it claims to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_nonexecutable_criteria import (
    _ELISION,
    _MAX_CRITERIA,
    _MAX_CRITERION_CHARS,
    find_nonexecutable_criteria,
)

# The shape that broke PR #5350: a pre_pr.py-passes line inside the PR body's
# own acceptance-criteria list, alongside criteria a diff reviewer can check.
_PR_5350_BODY = """## Summary

Fixes #4727.

## Acceptance criteria

- [x] `scripts/validation/pre_pr.py` gains a gate for the new artifact
- [x] Tests cover the positive and negative branches
- [x] `uv run python scripts/validation/pre_pr.py` passes

## Testing

- [x] `uv run --frozen python -m pytest tests/ci -q` passes locally
"""


def _body(*criteria: str) -> str:
    lines = ["## Acceptance criteria", ""]
    lines.extend(criteria)
    return "\n".join(lines) + "\n"


class TestDetectsCommandExecutionClaims:
    def test_detects_the_pr_5350_criterion(self) -> None:
        found = find_nonexecutable_criteria(_PR_5350_BODY)

        assert found == ["`uv run python scripts/validation/pre_pr.py` passes"]

    @pytest.mark.parametrize(
        "criterion",
        [
            "- [x] `uv run python scripts/validation/pre_pr.py` passes",
            "- [x] `pytest tests/ci -q` exits 0",
            "- `ruff check .` is green",
            "- Run `make build` and it completes successfully",
            "- [x] `scripts/validation/pre_pr.py` passes locally",
            "- [x] `pwsh -File build.ps1` returns zero",
            "- [x] `npm test` succeeds",
            "- [x] `$ pytest` passes",
            "- [x] `semgrep --config auto .` reports no findings",
            "* [x] `go test ./...` runs clean",
            "1. `gh pr checks` is green",
        ],
    )
    def test_detects_each_command_claim_shape(self, criterion: str) -> None:
        assert find_nonexecutable_criteria(_body(criterion)), criterion

    def test_folds_a_wrapped_criterion_into_one_entry(self) -> None:
        body = _body(
            "- [x] `uv run --frozen python scripts/validation/pre_pr.py`",
            "      passes",
        )

        assert find_nonexecutable_criteria(body) == [
            "`uv run --frozen python scripts/validation/pre_pr.py` passes"
        ]

    def test_returns_criteria_in_body_order(self) -> None:
        body = _body(
            "- [x] `pytest` passes",
            "- [ ] the parser rejects an empty ref",
            "- [x] `ruff check .` is green",
        )

        assert find_nonexecutable_criteria(body) == ["`pytest` passes", "`ruff check .` is green"]


class TestDoesNotOverFire:
    """Negative controls. A criterion the reviewer CAN check must stay in scope."""

    @pytest.mark.parametrize(
        "criterion",
        [
            "- [ ] The helper passes the new flag through to `run_gh`",
            "- [ ] `pre_pr.py` passes the changed-file list to ruff",
            "- [ ] `run_gh` passes",
            "- [ ] All tests pass",
            "- [ ] The build succeeds",
            "- [ ] `PARTIAL` is documented in the prompt",
            "- [ ] `scripts/ci/spec_prepare_context.py` renders the declaration",
            "- [ ] Coverage stays above 80%",
        ],
    )
    def test_leaves_verifiable_criteria_alone(self, criterion: str) -> None:
        assert find_nonexecutable_criteria(_body(criterion)) == []

    @pytest.mark.parametrize(
        "criterion",
        [
            # A command name and a result verb both appear, but the verb
            # governs the code under review, not the command. Scanning for the
            # two independently classified these away (PR #5451 review).
            "- [ ] The wrapper succeeds when `pytest` returns malformed output",
            "- [ ] The fallback passes when `ruff` reports an error",
            "- [ ] The wrapper returns zero when `pytest` passes",
            "- [ ] The gate stays green after `pytest` passes",
            "- [ ] The runner exits 0 unless `go test ./...` is green",
            "- [ ] `spec_prepare_context.py` is skipped if `pytest` passes",
            # The subject of the result verb is the script under test, and the
            # command it is conditioned on sits in the subordinate clause.
            # Truncating at "when" left `wrapper.py` returns zero, which reads
            # as run evidence on its own (PR #5451 review, round 2).
            "- [ ] `wrapper.py` returns zero when `pytest` passes",
        ],
    )
    def test_leaves_behavioral_contracts_in_scope(self, criterion: str) -> None:
        assert find_nonexecutable_criteria(_body(criterion)) == [], criterion

    @pytest.mark.parametrize(
        "criterion",
        [
            # Run evidence plus a real requirement in one bullet. Classifying
            # the bullet away takes the requirement with it, so the whole
            # bullet stays in scope (PR #5451 review, round 2).
            "- [ ] `pytest` passes locally and the parser rejects an empty ref",
            "- [ ] `ruff check .` is green, and the CLI exits 2 on a bad flag",
            "- [ ] `npm test` succeeds; the bundle stays under 200 KB",
            # Mirror shape: the requirement comes first, with no subordinator
            # joining the two halves (PR #5451 review, round 3).
            "- [ ] the parser rejects an empty ref and `pytest` passes",
            "- [x] The CLI exits 2 on a bad flag and `ruff check .` is green",
            # Same subject misattribution with no coordinator joining the
            # halves: the grammatical subject is the README, not the command
            # (PR #5451 review, round 4). Covered by the round-3 rule that the
            # command span must open the criterion, with no new code.
            "- [x] The README documents that `pytest` passes",
            "- [x] The changelog notes that `ruff check .` is green",
            "- [x] The docs claim `npm test` succeeds",
        ],
    )
    def test_leaves_a_compound_criterion_in_scope(self, criterion: str) -> None:
        assert find_nonexecutable_criteria(_body(criterion)) == [], criterion

    @pytest.mark.parametrize(
        "criterion",
        [
            "- [ ] `uv run python scripts/validation/pre_pr.py` passes",
            "- [ ] `pytest` passes",
            "- [~] `ruff check .` is green",
        ],
    )
    def test_leaves_an_unchecked_criterion_in_scope(self, criterion: str) -> None:
        """An unchecked box is an admitted gap, not something to wave through.

        `.github/PULL_REQUEST_TEMPLATE.md:73` says so directly: "Check a box
        only once the criterion is actually met; an unchecked box makes the
        spec-coverage signal report FAIL (non-blocking)." Classifying it `N/A`
        would erase that FAIL from the completeness count.
        """
        assert find_nonexecutable_criteria(_body(criterion)) == [], criterion

    @pytest.mark.parametrize(
        ("label", "body"),
        [
            (
                "blank line before the closing fence",
                "## Summary\n\nExample of a criteria section:\n\n"
                "```markdown\n## Acceptance Criteria\n\n- [x] `pytest` passes\n\n```\n\n"
                "## Notes\n\nNothing else.\n",
            ),
            (
                "unclosed fence running to the end of the body",
                "## Summary\n\n```markdown\n## Acceptance Criteria\n\n- [x] `pytest` passes\n",
            ),
            (
                "tilde fence inside a real acceptance section",
                "## Acceptance criteria\n\n- [x] renders for a body like this:\n\n"
                "~~~\n- [x] `ruff check .` is green\n\n~~~\n",
            ),
        ],
    )
    def test_ignores_a_fenced_sample_section(self, label: str, body: str) -> None:
        """Sample text must never take part in the gate.

        Each shape was verified to leak before the fence check existed. A
        closing fence on the line directly after the bullet does NOT leak, but
        only because `_bullets` folds that line into the bullet and the result
        tail then refuses it, which is an accident of two unrelated rules
        rather than a guarantee (PR #5451 review, round 3).
        """
        assert find_nonexecutable_criteria(body) == [], label

    def test_still_reads_criteria_after_a_fenced_block_closes(self) -> None:
        body = (
            "## Acceptance criteria\n\n"
            "```text\n"
            "- [x] `ruff check .` is green\n"
            "```\n\n"
            "- [x] `pytest` passes\n"
        )

        assert find_nonexecutable_criteria(body) == ["`pytest` passes"]

    @pytest.mark.parametrize(
        "heading",
        ["## Acceptance Criteria Verification", "## Non-Acceptance Criteria"],
    )
    def test_ignores_a_heading_that_only_contains_the_title(self, heading: str) -> None:
        body = f"{heading}\n\n- [x] `uv run python scripts/validation/pre_pr.py` passes\n"

        assert find_nonexecutable_criteria(body) == []

    def test_ignores_command_claims_outside_the_acceptance_section(self) -> None:
        body = (
            "## Testing\n\n"
            "- [x] `uv run python scripts/validation/pre_pr.py` passes\n\n"
            "## Author Pre-flight\n\n"
            "- [x] `uv run --frozen python -m pytest` passes\n"
        )

        assert find_nonexecutable_criteria(body) == []

    def test_stops_at_the_next_same_level_heading(self) -> None:
        body = (
            "## Acceptance criteria\n\n"
            "- [ ] parser handles an empty body\n\n"
            "## Testing\n\n"
            "- [x] `pytest` passes\n"
        )

        assert find_nonexecutable_criteria(body) == []

    def test_keeps_collecting_through_a_deeper_subheading(self) -> None:
        body = (
            "## Acceptance criteria\n\n"
            "### Validator\n\n"
            "- [x] `uv run python scripts/validation/pre_pr.py` passes\n"
        )

        assert find_nonexecutable_criteria(body) == [
            "`uv run python scripts/validation/pre_pr.py` passes"
        ]

    def test_ignores_bullets_before_any_heading(self) -> None:
        assert find_nonexecutable_criteria("- [ ] `pytest` passes\n\n## Summary\n") == []


class TestDegradesQuietly:
    @pytest.mark.parametrize("body", ["", "\n", "## Summary\n\nNo criteria here.\n"])
    def test_returns_empty_without_an_acceptance_section(self, body: str) -> None:
        assert find_nonexecutable_criteria(body) == []

    @pytest.mark.parametrize(
        "heading",
        [
            "## acceptance criteria",
            "### Acceptance Criteria",
            "## Acceptance Criterion",
            "## Acceptance Criteria ##",
        ],
    )
    def test_matches_the_heading_case_insensitively(self, heading: str) -> None:
        body = f"{heading}\n\n- [x] `pytest` passes\n"

        assert find_nonexecutable_criteria(body) == ["`pytest` passes"]

    def test_ignores_an_empty_code_span(self) -> None:
        assert find_nonexecutable_criteria(_body("- [ ] `` passes")) == []


class TestSanitizesInjectedText:
    def test_strips_leading_markdown_structure(self) -> None:
        found = find_nonexecutable_criteria(_body("- [x] ## `pytest` passes"))

        assert found == ["`pytest` passes"]

    def test_strips_control_characters(self) -> None:
        found = find_nonexecutable_criteria(_body("- [x] `pytest`\x07 passes"))

        assert found == ["`pytest` passes"]

    def test_truncates_a_long_criterion(self) -> None:
        # The length lives in the command itself. Prose in front of the command
        # span would make this a compound criterion, which is out of scope by
        # design (PR #5451 review, round 3).
        long_command = "pytest " + " ".join(f"tests/ci/case_{index}.py" for index in range(12))
        found = find_nonexecutable_criteria(_body(f"- [x] `{long_command}` passes"))

        assert len(found) == 1
        assert len(found[0]) <= _MAX_CRITERION_CHARS
        assert _ELISION in found[0]

    def test_a_truncated_criterion_still_shows_what_was_classified(self) -> None:
        """The entry has to carry its own evidence.

        A declaration entry that kept the command and dropped the result verb
        left the reviewer nothing to check the classification against
        (PR #5451 review, round 4).
        """
        long_command = "pytest " + " ".join(f"tests/ci/case_{index}.py" for index in range(12))
        found = find_nonexecutable_criteria(_body(f"- [x] `{long_command}` passes"))

        assert len(found) == 1
        assert found[0].startswith("`pytest tests/ci/case_0.py")
        assert found[0].endswith("passes")

    def test_deduplicates_repeated_criteria(self) -> None:
        body = _body("- [x] `pytest` passes", "- [x] `pytest` passes")

        assert find_nonexecutable_criteria(body) == ["`pytest` passes"]

    def test_caps_the_number_of_criteria(self) -> None:
        body = _body(*[f"- [x] `pytest tests/case_{index}.py` passes" for index in range(40)])

        assert len(find_nonexecutable_criteria(body)) == _MAX_CRITERIA
