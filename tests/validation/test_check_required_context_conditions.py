"""Tests for scripts/validation/check_required_context_conditions.py.

ADR-101 requirement 1 asks for an advisory lint over the workflows that produce a
pinned required context. These tests write small workflow trees to a temporary
directory, so every finding kind and every non-finding is exercised on a known
input, then run the module once against this repository's own workflows.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import pytest
from check_required_context_conditions import (
    KIND_JOB,
    KIND_PRODUCERS,
    KIND_RELOCATED,
    KIND_STEP,
    grouped_lines,
    lint,
    load_workflows,
    producing_jobs,
)

from tests.validation.required_context_helpers import (
    CONTEXT,
    job_body,
    kinds,
    lint_one,
    write_workflow,
)


class TestStepCondition:
    @pytest.mark.parametrize(
        ("condition", "source"),
        [
            ("needs.check.outputs.go == 'true'", "needs.*.outputs"),
            ("needs['check'].outputs.go == 'true'", "needs.*.outputs"),
            ("github.event_name == 'push'", "github.event_name"),
            ("github['event_name'] != 'merge_group'", "github.event_name"),
            ("github.actor != 'dependabot[bot]'", "github.actor"),
            ("github['actor'] == 'me'", "github.actor"),
        ],
    )
    def test_each_named_source_is_flagged(
        self, tmp_path: Path, condition: str, source: str
    ) -> None:
        steps = f"      - name: Guarded\n        if: {condition}\n        run: echo hi\n"

        findings, producers = lint_one(tmp_path, job_body(steps=steps))

        assert len(producers) == 1
        assert kinds(findings) == [KIND_STEP]
        assert source in findings[0].detail
        assert findings[0].step == "Guarded"

    def test_combined_sources_are_all_named(self, tmp_path: Path) -> None:
        steps = (
            "      - name: Both\n"
            "        if: github.event_name == 'push' && github.actor != 'bot'\n"
            "        run: echo hi\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert "github.event_name" in findings[0].detail
        assert "github.actor" in findings[0].detail

    @pytest.mark.parametrize(
        "condition",
        [
            "always()",
            "${{ !cancelled() }}",
            "success()",
            "needs.check.result == 'success'",
            "steps.decide.outputs.skip != 'true'",
            "matrix.partition == 'bulk'",
            "github.ref_name == 'main'",
            "github.event.pull_request.draft == false",
            "true",
        ],
    )
    def test_conditions_outside_the_three_sources_pass(
        self, tmp_path: Path, condition: str
    ) -> None:
        steps = f"      - name: Fine\n        if: {condition}\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    def test_a_source_in_a_run_body_is_not_a_condition(self, tmp_path: Path) -> None:
        steps = "      - name: Reads\n        run: echo ${{ needs.check.outputs.go }}\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    def test_a_boolean_if_is_read_without_crashing(self, tmp_path: Path) -> None:
        steps = "      - name: Literal\n        if: false\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    def test_unnamed_step_is_labelled_by_id_then_index(self, tmp_path: Path) -> None:
        steps = (
            "      - id: by-id\n        if: github.actor == 'a'\n        run: echo 1\n"
            "      - if: github.actor == 'a'\n        run: echo 2\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert [f.step for f in findings] == ["by-id", "step[1]"]

    def test_a_job_without_steps_is_read_as_clean(self, tmp_path: Path) -> None:
        body = (
            "on: pull_request\njobs:\n  gate:\n    name: Run Python Tests\n"
            "    uses: ./.github/workflows/reusable.yml\n"
        )

        findings, producers = lint_one(tmp_path, body)

        assert len(producers) == 1
        assert findings == []


class TestRelocatedCondition:
    """The relocation ADR-101 says defeats the syntactic rule, followed one level."""

    def test_step_output_fed_by_the_event_name_is_flagged(self, tmp_path: Path) -> None:
        steps = (
            "      - id: should-run\n"
            "        env:\n"
            "          EVENT_NAME: ${{ github.event_name }}\n"
            "        run: python decide.py\n"
            "      - name: Real work\n"
            "        if: steps.should-run.outputs.skip != 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_RELOCATED]
        assert findings[0].step == "Real work"
        assert "should-run" in findings[0].detail
        assert "github.event_name" in findings[0].detail

    def test_environment_spelling_in_a_script_body_counts(self, tmp_path: Path) -> None:
        steps = (
            "      - id: gate\n"
            "        run: |\n"
            '          if [ "$GITHUB_ACTOR" = bot ]; then echo skip=true >> $GITHUB_OUTPUT; fi\n'
            "      - name: Work\n"
            "        if: steps.gate.outputs.skip != 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_RELOCATED]
        assert "github.actor" in findings[0].detail

    def test_step_output_fed_by_another_jobs_output_is_flagged(self, tmp_path: Path) -> None:
        steps = (
            "      - id: should-run\n"
            "        env:\n"
            "          CHANGED: ${{ needs.check-paths.outputs.changed }}\n"
            "        run: python decide.py\n"
            "      - name: Work\n"
            "        if: steps.should-run.outputs.skip != 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_RELOCATED]
        assert "needs.*.outputs" in findings[0].detail

    def test_a_step_output_from_a_clean_step_passes(self, tmp_path: Path) -> None:
        steps = (
            "      - id: build\n        run: echo built=true >> $GITHUB_OUTPUT\n"
            "      - name: Work\n"
            "        if: steps.build.outputs.built == 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    def test_reading_an_unknown_step_id_does_not_crash(self, tmp_path: Path) -> None:
        steps = (
            "      - name: Work\n"
            "        if: steps.ghost.outputs.x == '1'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    def test_a_direct_reference_and_a_relocation_are_both_reported(
        self, tmp_path: Path
    ) -> None:
        steps = (
            "      - id: g\n        run: echo $GITHUB_EVENT_NAME\n"
            "      - name: Both\n"
            "        if: github.actor == 'a' && steps.g.outputs.skip != 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_STEP, KIND_RELOCATED]

    def test_a_repeated_read_of_one_step_is_reported_once(self, tmp_path: Path) -> None:
        steps = (
            "      - id: g\n        run: echo $GITHUB_EVENT_NAME\n"
            "      - name: Twice\n"
            "        if: steps.g.outputs.a == '1' && steps.g.outputs.b == '2'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_RELOCATED]


class TestJobCondition:
    def test_job_gated_on_another_jobs_output_is_flagged(self, tmp_path: Path) -> None:
        findings, _ = lint_one(
            tmp_path, job_body(condition="needs.check.outputs.go == 'true'")
        )

        assert kinds(findings) == [KIND_JOB]
        assert findings[0].step == ""

    @pytest.mark.parametrize(
        "condition",
        [
            "${{ !cancelled() }}",
            "needs.test.result == 'success'",
            "github.event_name != 'merge_group'",
        ],
    )
    def test_control_plane_results_and_event_terms_pass_at_job_level(
        self, tmp_path: Path, condition: str
    ) -> None:
        """The ADR lint names step conditions. `needs.*.result` is the permitted input."""
        findings, _ = lint_one(tmp_path, job_body(condition=condition))

        assert findings == []


class TestProducerCount:
    def test_a_second_job_with_the_same_name_is_a_pass_through(self, tmp_path: Path) -> None:
        body = """\
            on: pull_request
            jobs:
              real:
                name: Run Python Tests
                runs-on: ubuntu-latest
                steps:
                  - run: pytest
              skip:
                name: Run Python Tests
                runs-on: ubuntu-latest
                steps:
                  - run: echo skipped
            """

        findings, producers = lint_one(tmp_path, body)

        assert len(producers) == 2
        assert kinds(findings) == [KIND_PRODUCERS]
        assert "2 jobs" in findings[0].detail

    def test_two_workflows_producing_one_context_are_counted_together(
        self, tmp_path: Path
    ) -> None:
        workflows = tmp_path / "workflows"
        one = "on: push\njobs:\n  a:\n    name: Run Python Tests\n    steps: []\n"
        write_workflow(workflows, "one.yml", one)
        write_workflow(workflows, "two.yml", one)

        findings, _ = lint(load_workflows(workflows), (CONTEXT,))

        assert kinds(findings) == [KIND_PRODUCERS]

    def test_a_pinned_context_with_no_producer_is_reported(self, tmp_path: Path) -> None:
        body = "on: push\njobs:\n  a:\n    name: Something else\n    steps: []\n"

        findings, producers = lint_one(tmp_path, body)

        assert producers == []
        assert kinds(findings) == [KIND_PRODUCERS]
        assert "no job produces" in findings[0].detail

    def test_a_distinct_skipped_name_is_not_a_second_producer(self, tmp_path: Path) -> None:
        """The plugin version bump shape: the pass-through carries a different string."""
        body = """\
            on: pull_request
            jobs:
              validate:
                name: Validate Plugin Version Bump
                steps: []
              skip-validation:
                name: Validate Plugin Version Bump (Skipped)
                steps: []
            """

        findings, producers = lint_one(tmp_path, body, ("Validate Plugin Version Bump",))

        assert [p.job_id for p in producers] == ["validate"]
        assert findings == []

    def test_a_job_without_a_name_is_identified_by_its_id(self, tmp_path: Path) -> None:
        body = "on: push\njobs:\n  Run Python Tests:\n    steps: []\n"

        _, producers = lint_one(tmp_path, body)

        assert [p.job_id for p in producers] == ["Run Python Tests"]

    def test_literal_names_never_match_by_prefix(self, tmp_path: Path) -> None:
        """`Validate PR` must not claim `Validate PR title`."""
        body = "on: push\njobs:\n  a:\n    name: Validate PR\n    steps: []\n"
        documents = load_workflows(self._dir(tmp_path, body))

        producers = producing_jobs(documents, ("Validate PR", "Validate PR title"))

        assert [p.context for p in producers] == ["Validate PR"]

    def test_an_expression_name_matches_every_context_with_its_prefix(
        self, tmp_path: Path
    ) -> None:
        body = (
            "on: push\njobs:\n  analyze:\n    name: Analyze (${{ matrix.language }})\n"
            "    steps: []\n"
        )
        documents = load_workflows(self._dir(tmp_path, body))

        producers = producing_jobs(documents, ("Analyze (python)", "Analyze (actions)", "Other"))

        assert sorted(p.context for p in producers) == ["Analyze (actions)", "Analyze (python)"]

    @staticmethod
    def _dir(tmp_path: Path, body: str) -> Path:
        workflows = tmp_path / "workflows"
        write_workflow(workflows, "wf.yml", body)
        return workflows


class TestGrouping:
    def test_steps_behind_one_condition_collapse_to_one_line(self, tmp_path: Path) -> None:
        steps = "".join(
            f"      - name: s{i}\n        if: github.actor != 'bot'\n        run: echo {i}\n"
            for i in range(3)
        )
        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        lines = grouped_lines(findings)

        assert len(findings) == 3
        assert len(lines) == 1
        assert lines[0].endswith("(3 steps)")

    def test_a_single_step_is_not_pluralised(self, tmp_path: Path) -> None:
        steps = "      - name: only\n        if: github.actor != 'bot'\n        run: echo 1\n"
        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert grouped_lines(findings)[0].endswith("(1 step)")

    def test_job_level_findings_carry_no_step_suffix(self, tmp_path: Path) -> None:
        findings, _ = lint_one(tmp_path, job_body(condition="needs.a.outputs.x == '1'"))

        assert "step" not in grouped_lines(findings)[0].split(": ")[-1]

    def test_render_names_the_step_when_there_is_one(self, tmp_path: Path) -> None:
        steps = "      - name: named\n        if: github.actor != 'bot'\n        run: echo 1\n"
        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings[0].render().startswith(f"[{KIND_STEP}] {CONTEXT}: wf.yml:gate:named:")
