"""Tests for scripts/validation/check_required_context_conditions.py.

ADR-101 requirement 1 asks for an advisory lint over the workflows that produce a
pinned required context. These tests write small workflow trees to a temporary
directory, so every finding kind and every non-finding is exercised on a known
input, then run the module once against this repository's own workflows.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_required_context_conditions as lint_mod
from check_required_context_conditions import (
    EXIT_CONFIG,
    EXIT_FINDINGS,
    EXIT_OK,
    KIND_JOB,
    KIND_PRODUCERS,
    KIND_RELOCATED,
    KIND_STEP,
    WorkflowLoadError,
    grouped_lines,
    lint,
    load_workflows,
    main,
    producing_jobs,
    validate_required_context_conditions,
)

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS

CONTEXT = "Run Python Tests"


def _write(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(textwrap.dedent(body), encoding="utf-8")


def _lint_one(tmp_path: Path, body: str, contexts: tuple[str, ...] = (CONTEXT,)):
    workflows = tmp_path / "workflows"
    _write(workflows, "wf.yml", body)
    documents = load_workflows(workflows)
    return lint(documents, contexts)


def _kinds(findings: list) -> list[str]:
    return [f.kind for f in findings]


def _job(condition: str = "", steps: str = "      - run: echo ok\n") -> str:
    header = f"    if: {condition}\n" if condition else ""
    return (
        "on: pull_request\njobs:\n  gate:\n    name: Run Python Tests\n"
        f"{header}    runs-on: ubuntu-latest\n    steps:\n{steps}"
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

        findings, producers = _lint_one(tmp_path, _job(steps=steps))

        assert len(producers) == 1
        assert _kinds(findings) == [KIND_STEP]
        assert source in findings[0].detail
        assert findings[0].step == "Guarded"

    def test_combined_sources_are_all_named(self, tmp_path: Path) -> None:
        steps = (
            "      - name: Both\n"
            "        if: github.event_name == 'push' && github.actor != 'bot'\n"
            "        run: echo hi\n"
        )

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

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

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert findings == []

    def test_a_source_in_a_run_body_is_not_a_condition(self, tmp_path: Path) -> None:
        steps = "      - name: Reads\n        run: echo ${{ needs.check.outputs.go }}\n"

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert findings == []

    def test_a_boolean_if_is_read_without_crashing(self, tmp_path: Path) -> None:
        steps = "      - name: Literal\n        if: false\n        run: echo hi\n"

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert findings == []

    def test_unnamed_step_is_labelled_by_id_then_index(self, tmp_path: Path) -> None:
        steps = (
            "      - id: by-id\n        if: github.actor == 'a'\n        run: echo 1\n"
            "      - if: github.actor == 'a'\n        run: echo 2\n"
        )

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert [f.step for f in findings] == ["by-id", "step[1]"]

    def test_a_job_without_steps_is_read_as_clean(self, tmp_path: Path) -> None:
        body = (
            "on: pull_request\njobs:\n  gate:\n    name: Run Python Tests\n"
            "    uses: ./.github/workflows/reusable.yml\n"
        )

        findings, producers = _lint_one(tmp_path, body)

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

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert _kinds(findings) == [KIND_RELOCATED]
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

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert _kinds(findings) == [KIND_RELOCATED]
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

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert _kinds(findings) == [KIND_RELOCATED]
        assert "needs.*.outputs" in findings[0].detail

    def test_a_step_output_from_a_clean_step_passes(self, tmp_path: Path) -> None:
        steps = (
            "      - id: build\n        run: echo built=true >> $GITHUB_OUTPUT\n"
            "      - name: Work\n"
            "        if: steps.build.outputs.built == 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert findings == []

    def test_reading_an_unknown_step_id_does_not_crash(self, tmp_path: Path) -> None:
        steps = (
            "      - name: Work\n"
            "        if: steps.ghost.outputs.x == '1'\n"
            "        run: pytest\n"
        )

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

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

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert _kinds(findings) == [KIND_STEP, KIND_RELOCATED]

    def test_a_repeated_read_of_one_step_is_reported_once(self, tmp_path: Path) -> None:
        steps = (
            "      - id: g\n        run: echo $GITHUB_EVENT_NAME\n"
            "      - name: Twice\n"
            "        if: steps.g.outputs.a == '1' && steps.g.outputs.b == '2'\n"
            "        run: pytest\n"
        )

        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert _kinds(findings) == [KIND_RELOCATED]


class TestJobCondition:
    def test_job_gated_on_another_jobs_output_is_flagged(self, tmp_path: Path) -> None:
        findings, _ = _lint_one(
            tmp_path, _job(condition="needs.check.outputs.go == 'true'")
        )

        assert _kinds(findings) == [KIND_JOB]
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
        findings, _ = _lint_one(tmp_path, _job(condition=condition))

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

        findings, producers = _lint_one(tmp_path, body)

        assert len(producers) == 2
        assert _kinds(findings) == [KIND_PRODUCERS]
        assert "2 jobs" in findings[0].detail

    def test_two_workflows_producing_one_context_are_counted_together(
        self, tmp_path: Path
    ) -> None:
        workflows = tmp_path / "workflows"
        one = "on: push\njobs:\n  a:\n    name: Run Python Tests\n    steps: []\n"
        _write(workflows, "one.yml", one)
        _write(workflows, "two.yml", one)

        findings, _ = lint(load_workflows(workflows), (CONTEXT,))

        assert _kinds(findings) == [KIND_PRODUCERS]

    def test_a_pinned_context_with_no_producer_is_reported(self, tmp_path: Path) -> None:
        body = "on: push\njobs:\n  a:\n    name: Something else\n    steps: []\n"

        findings, producers = _lint_one(tmp_path, body)

        assert producers == []
        assert _kinds(findings) == [KIND_PRODUCERS]
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

        findings, producers = _lint_one(tmp_path, body, ("Validate Plugin Version Bump",))

        assert [p.job_id for p in producers] == ["validate"]
        assert findings == []

    def test_a_job_without_a_name_is_identified_by_its_id(self, tmp_path: Path) -> None:
        body = "on: push\njobs:\n  Run Python Tests:\n    steps: []\n"

        _, producers = _lint_one(tmp_path, body)

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
        _write(workflows, "wf.yml", body)
        return workflows


class TestLoadWorkflows:
    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(WorkflowLoadError, match="not found"):
            load_workflows(tmp_path / "absent")

    def test_invalid_yaml_raises_instead_of_reading_as_empty(self, tmp_path: Path) -> None:
        _write(tmp_path, "bad.yml", "jobs: [unclosed\n")

        with pytest.raises(WorkflowLoadError, match="bad.yml"):
            load_workflows(tmp_path)

    def test_a_non_mapping_top_level_raises(self, tmp_path: Path) -> None:
        _write(tmp_path, "list.yml", "- a\n- b\n")

        with pytest.raises(WorkflowLoadError, match="not a mapping"):
            load_workflows(tmp_path)

    def test_an_empty_file_raises(self, tmp_path: Path) -> None:
        _write(tmp_path, "empty.yml", "")

        with pytest.raises(WorkflowLoadError, match="not a mapping"):
            load_workflows(tmp_path)

    def test_yaml_and_yml_extensions_are_both_read(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.yml", "on: push\njobs: {}\n")
        _write(tmp_path, "b.yaml", "on: push\njobs: {}\n")

        assert sorted(load_workflows(tmp_path)) == ["a.yml", "b.yaml"]

    def test_a_workflow_with_no_jobs_mapping_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        _write(tmp_path, "nojobs.yml", "on: push\njobs: not-a-mapping\n")
        documents = load_workflows(tmp_path)

        assert producing_jobs(documents, (CONTEXT,)) == []

    def test_a_job_body_that_is_not_a_mapping_is_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "odd.yml", "on: push\njobs:\n  a: just-a-string\n")
        documents = load_workflows(tmp_path)

        assert producing_jobs(documents, (CONTEXT,)) == []


class TestGrouping:
    def test_steps_behind_one_condition_collapse_to_one_line(self, tmp_path: Path) -> None:
        steps = "".join(
            f"      - name: s{i}\n        if: github.actor != 'bot'\n        run: echo {i}\n"
            for i in range(3)
        )
        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        lines = grouped_lines(findings)

        assert len(findings) == 3
        assert len(lines) == 1
        assert lines[0].endswith("(3 steps)")

    def test_a_single_step_is_not_pluralised(self, tmp_path: Path) -> None:
        steps = "      - name: only\n        if: github.actor != 'bot'\n        run: echo 1\n"
        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert grouped_lines(findings)[0].endswith("(1 step)")

    def test_job_level_findings_carry_no_step_suffix(self, tmp_path: Path) -> None:
        findings, _ = _lint_one(tmp_path, _job(condition="needs.a.outputs.x == '1'"))

        assert "step" not in grouped_lines(findings)[0].split(": ")[-1]

    def test_render_names_the_step_when_there_is_one(self, tmp_path: Path) -> None:
        steps = "      - name: named\n        if: github.actor != 'bot'\n        run: echo 1\n"
        findings, _ = _lint_one(tmp_path, _job(steps=steps))

        assert findings[0].render().startswith(f"[{KIND_STEP}] {CONTEXT}: wf.yml:gate:named:")


class TestMain:
    def _tree(self, tmp_path: Path, body: str) -> Path:
        workflows = tmp_path / "workflows"
        _write(workflows, "wf.yml", body)
        return workflows

    def _flagged(self) -> str:
        return _job(steps="      - name: g\n        if: github.actor == 'a'\n        run: echo 1\n")

    def test_findings_exit_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        workflows = self._tree(tmp_path, self._flagged())

        code = main(["--workflows-dir", str(workflows)])

        assert code == EXIT_FINDINGS
        assert "1 findings; examined 1 workflows, 1 pinned contexts, 1 producing jobs" in (
            capsys.readouterr().out
        )

    def test_advisory_reports_but_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        workflows = self._tree(tmp_path, self._flagged())

        code = main(["--workflows-dir", str(workflows), "--advisory"])

        assert code == EXIT_OK
        assert "[step-condition]" in capsys.readouterr().out

    def test_clean_tree_exits_zero_and_still_prints_the_examined_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        workflows = self._tree(tmp_path, _job())

        code = main(["--workflows-dir", str(workflows)])

        assert code == EXIT_OK
        assert "0 findings; examined 1 workflows" in capsys.readouterr().out

    def test_verbose_lists_every_step(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        steps = "".join(
            f"      - name: s{i}\n        if: github.actor != 'bot'\n        run: echo {i}\n"
            for i in range(2)
        )
        workflows = self._tree(tmp_path, _job(steps=steps))

        main(["--workflows-dir", str(workflows), "--verbose", "--advisory"])

        out = capsys.readouterr().out
        assert "wf.yml:gate:s0" in out
        assert "wf.yml:gate:s1" in out

    def test_unparseable_workflow_exits_two_even_when_advisory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workflows = tmp_path / "workflows"
        _write(workflows, "bad.yml", "jobs: [unclosed\n")

        code = main(["--workflows-dir", str(workflows), "--advisory"])

        assert code == EXIT_CONFIG
        assert "bad.yml" in capsys.readouterr().err

    def test_missing_directory_exits_two(self, tmp_path: Path) -> None:
        assert main(["--workflows-dir", str(tmp_path / "absent")]) == EXIT_CONFIG


class TestPrePrGate:
    def test_gate_prints_findings_and_returns_true(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(lint_mod, "REQUIRED_CONTEXTS", frozenset({CONTEXT}))
        _write(
            tmp_path / ".github" / "workflows",
            "wf.yml",
            _job(steps="      - name: g\n        if: github.actor == 'a'\n        run: echo 1\n"),
        )

        assert validate_required_context_conditions(tmp_path) is True

        out = capsys.readouterr().out
        assert "required-context-conditions: [step-condition]" in out
        assert "required-context-conditions: 1 findings" in out

    def test_gate_returns_true_and_reports_when_a_workflow_does_not_parse(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path / ".github" / "workflows", "bad.yml", "jobs: [unclosed\n")

        assert validate_required_context_conditions(tmp_path) is True

        assert "bad.yml" in capsys.readouterr().err

    def test_gate_returns_true_when_there_is_no_workflow_directory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert validate_required_context_conditions(tmp_path) is True

        assert "not found" in capsys.readouterr().err


class TestRealCorpus:
    """Rule 13 (`.claude/rules/ci-scripts.md`): show the gate against the full corpus."""

    def test_every_pinned_context_has_a_producing_job_in_this_repository(self) -> None:
        documents = load_workflows(REPO_ROOT / ".github" / "workflows")
        producers = producing_jobs(documents, REQUIRED_CONTEXTS)

        produced = {p.context for p in producers}

        assert produced == set(REQUIRED_CONTEXTS)
        assert len(documents) > 20

    def test_the_real_corpus_runs_clean_of_config_errors_under_advisory(self) -> None:
        code = main(["--advisory"])

        assert code == EXIT_OK

    def test_the_known_relocations_the_adr_names_are_seen(self) -> None:
        """ADR-101 names the step-relocated required contexts; the lint must see them."""
        documents = load_workflows(REPO_ROOT / ".github" / "workflows")
        findings, _ = lint(documents, REQUIRED_CONTEXTS)

        flagged = {(f.workflow, f.context) for f in findings}

        assert ("validate-paths.yml", "Validate Path Normalization") in flagged
        assert ("validate-generated-agents.yml", "Validate Generated Files") in flagged
        assert ("pr-validation.yml", "Validate PR") in flagged
        assert ("semantic-pr-title-check.yml", "Validate PR title") in flagged
        assert ("codeql-analysis.yml", "Analyze (python)") in flagged
