"""The declaration reaches the traceability reviewer as well (issue #5366).

`.github/workflows/ai-spec-validation.yml` builds `spec_context` once and hands
the same string to two steps: traceability (analyst,
`spec-trace-requirements.md`) and completeness (critic,
`spec-check-completeness.md`). Only the completeness prompt carries the
hint-not-override carve-out, so anything the declaration says arrives at the
analyst with no prompt-side qualification behind it.

Two consequences, fixed in two commits and pinned here:

- The declaration used to say "Treat each one as N/A ... do NOT emit PARTIAL or
  FAIL" without qualification. Naming completeness as the actor fixed the
  instruction half.
- Naming the actor still leaves the analyst holding a list of criteria with
  nothing saying coverage applies to them. Traceability decides whether a
  requirement is covered at all, which makes it the consumer where a classifier
  false positive costs the most, so the declaration says so directly.

`tests/ci/test_spec_prepare_context.py` covers the hint-not-override wording.
This file covers the part that is specific to the second consumer: that the
shared context really does feed both steps, and that the text tells the analyst
coverage still applies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from scripts.ci.spec_prepare_context import run  # noqa: E402

_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ai-spec-validation.yml"
_JOB = "validate-spec"
_CONTEXT_EXPRESSION = "${{ steps.prepare-context.outputs.spec_context }}"

_TRACEABILITY_PROMPT = ".github/prompts/spec-trace-requirements.md"
_COMPLETENESS_PROMPT = ".github/prompts/spec-check-completeness.md"

# Run evidence beside a real requirement, so a declaration is rendered and
# there is something a misfire could drop from coverage.
_PR_BODY = (
    "## Acceptance criteria\n\n"
    "- [x] `uv run python scripts/validation/pre_pr.py` passes\n"
    "- [ ] the parser rejects an empty ref with a non-zero exit\n"
)


def _steps_using_shared_context() -> dict[str, dict[str, Any]]:
    """Map prompt file to the step fed the shared `spec_context`."""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"][_JOB]["steps"]
    return {
        str(step["with"]["prompt-file"]): step
        for step in steps
        if isinstance(step, dict)
        and isinstance(step.get("with"), dict)
        and step["with"].get("additional-context") == _CONTEXT_EXPRESSION
        and "prompt-file" in step["with"]
    }


@pytest.fixture(scope="module")
def declaration(tmp_path_factory: pytest.TempPathFactory) -> str:
    """The real `spec_context`, built through `run()`, as one normalized line.

    Normalized because the block is hard-wrapped for the reviewer, so a
    sentence that reads as one phrase is split across list entries in the
    source. Asserting on the wrapped form would pin the wrap points rather than
    the wording, and a reflow that changed no instruction would fail.
    """
    tmp_path = tmp_path_factory.mktemp("spec_context")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("content", encoding="utf-8")
    out_file = tmp_path / "out.txt"
    env = {
        "SPEC_FILE": str(spec_file),
        "INCREMENTAL_SCOPE": "",
        "PR_BODY": _PR_BODY,
        "GITHUB_OUTPUT": str(out_file),
    }

    with patch.dict(os.environ, env):
        assert run() == 0

    context = out_file.read_text(encoding="utf-8")
    assert "## Non-Executable Criteria Declaration" in context, (
        "No declaration was rendered, so every assertion about its content "
        "below would pass vacuously."
    )
    return " ".join(context.split())


class TestBothReviewersReadTheSameDeclaration:
    def test_the_traceability_step_receives_the_shared_context(self) -> None:
        steps = _steps_using_shared_context()

        assert _TRACEABILITY_PROMPT in steps, (
            f"The traceability step no longer reads {_CONTEXT_EXPRESSION}. "
            f"Steps that do: {sorted(steps)}. If the declaration stopped "
            "reaching this prompt then the coverage sentence below is no "
            "longer load-bearing, so re-think this file rather than deleting "
            "the sentence."
        )

    def test_the_completeness_step_receives_the_same_context(self) -> None:
        """Control: the shared-source premise, not just one consumer."""
        steps = _steps_using_shared_context()

        assert _COMPLETENESS_PROMPT in steps
        assert len(steps) >= 2, (
            "Only one step reads the shared context, so the two consumers this "
            f"file exists to keep in step no longer both exist: {sorted(steps)}"
        )


class TestTheDeclarationSplitsTheListForTraceability:
    """Both halves, because either one alone reintroduces a false failure.

    Telling the analyst to trace nothing drops real requirements from
    coverage. Telling it to trace everything sends pure run evidence, which
    has no implementation, to `NOT_COVERED`, and
    `scripts/ai_review_common/verdict.py` blocks on the trace verdict exactly
    as it blocks on completeness. That would move the issue #5366 false
    failure rather than remove it.
    """

    def test_na_is_scoped_to_the_command_not_the_requirement(self, declaration: str) -> None:
        assert "N/A here refers to repeating the command" in declaration
        assert "never to a requirement the diff is meant to establish" in declaration

    def test_a_behavioral_contract_is_still_traced(self, declaration: str) -> None:
        assert "an entry that reads as a behavioral contract is a requirement" in declaration
        assert "do NOT drop it from coverage" in declaration

    def test_pure_run_evidence_is_skipped_rather_than_not_covered(self, declaration: str) -> None:
        assert "An entry that is only run evidence names no requirement to trace" in declaration
        assert "skip it rather than recording it NOT_COVERED" in declaration

    def test_the_exemption_names_completeness_as_its_actor(self, declaration: str) -> None:
        """The instruction half, so an unscoped N/A cannot come back.

        Without an actor the analyst reads "mark it N/A" as addressed to it.
        """
        assert "completeness should mark it N/A" in declaration

    def test_the_coverage_sentence_precedes_the_listed_criteria(self, declaration: str) -> None:
        """A limit printed after the list is one the reader may not reach."""
        coverage_at = declaration.index("do NOT drop it from coverage")
        first_criterion_at = declaration.index("- `uv run python")

        assert coverage_at < first_criterion_at


class TestUndeclaredRunEvidenceStillReachesTraceability:
    """The classifier under-fires by design, so the prompt carries these alone.

    `find_nonexecutable_criteria` reads only inline code spans. A criterion
    naming its command in prose produces no declaration, so nothing in the
    context tells either reviewer anything about it. Completeness has a
    standalone rule for that case; traceability's rules were briefly gated on
    a declaration existing, which left this shape landing in `NOT_COVERED`.

    This pins the premise rather than the prompt text: that these shapes really
    do arrive with no declaration, which is what makes the standalone rules in
    `tests/ci/test_spec_trace_prompt_contract.py` load-bearing rather than
    redundant.
    """

    @pytest.mark.parametrize(
        "criterion",
        [
            "- [x] All tests pass",
            "- [x] The build succeeds",
            "- [x] the full suite is green",
        ],
    )
    def test_prose_run_evidence_produces_no_declaration(
        self, criterion: str, tmp_path: Path
    ) -> None:
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content", encoding="utf-8")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "",
            "PR_BODY": f"## Acceptance criteria\n\n{criterion}\n",
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            assert run() == 0

        context = out_file.read_text(encoding="utf-8")

        assert "## Non-Executable Criteria Declaration" not in context, (
            f"{criterion!r} produced a declaration. If the classifier now "
            "catches prose run evidence, the traceability prompt's standalone "
            "rules are no longer the only thing covering this shape and this "
            "test should be re-thought rather than deleted."
        )

    def test_a_code_span_command_does_produce_one(self, tmp_path: Path) -> None:
        """Control: the absence above is about the shape, not a broken fixture."""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("content", encoding="utf-8")
        out_file = tmp_path / "out.txt"
        env = {
            "SPEC_FILE": str(spec_file),
            "INCREMENTAL_SCOPE": "",
            "PR_BODY": "## Acceptance criteria\n\n- [x] `pytest` passes\n",
            "GITHUB_OUTPUT": str(out_file),
        }

        with patch.dict(os.environ, env):
            assert run() == 0

        assert "## Non-Executable Criteria Declaration" in out_file.read_text(encoding="utf-8")
