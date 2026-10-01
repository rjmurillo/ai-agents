"""Review-driven cases for check_required_context_conditions.py.

Findings from the second and third security passes and from the automated review
of this pull request. Each class names the review it answers. The first-round
hardening cases live in test_check_required_context_conditions_hardening.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import pytest
import required_context_sources as sources
from check_required_context_conditions import (
    KIND_RELOCATED,
    KIND_STEP,
    KIND_UNATTRIBUTED,
    KIND_UNSCANNED,
    lint,
    load_workflows,
    main,
)

from tests.validation.required_context_helpers import (
    CONTEXT,
    job_body,
    kinds,
    lint_one,
    write_workflow,
)

ENV_JOB = """\
    on: pull_request
    jobs:
      gate:
        name: Run Python Tests
        env:
          EVENT: ${{ github.event_name }}
        steps:
          - id: decide
            run: |
              %s
          - name: Work
            if: steps.decide.outputs.skip != 'true'
            run: pytest
    """


class TestSecondReviewFindings:
    """The second security pass: case, shell env reads, budgets and a huge integer."""

    @pytest.mark.parametrize(
        "read",
        ['echo "$EVENT"', "echo ${EVENT}", "Write-Host $env:EVENT", "echo ${{ env['EVENT'] }}"],
    )
    def test_shell_and_bracket_env_reads_carry_the_taint(self, tmp_path: Path, read: str) -> None:
        findings, _ = lint_one(tmp_path, ENV_JOB % read)

        assert kinds(findings) == [KIND_RELOCATED]
        assert "github.event_name" in findings[0].detail

    def test_an_env_defined_from_a_tainted_env_is_tainted(self, tmp_path: Path) -> None:
        body = """\
            on: pull_request
            env:
              BASE: ${{ github.actor }}
            jobs:
              gate:
                name: Run Python Tests
                env:
                  DERIVED: ${{ env.BASE }}-x
                steps:
                  - name: Work
                    if: env.DERIVED != 'a-x'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert kinds(findings) == [KIND_RELOCATED]
        assert "github.actor" in findings[0].detail

    def test_an_unrelated_dollar_name_is_not_a_taint(self, tmp_path: Path) -> None:
        findings, _ = lint_one(tmp_path, ENV_JOB % 'echo "$HOME $OTHER"')

        assert findings == []

    def test_step_ids_and_env_names_are_matched_case_insensitively(self, tmp_path: Path) -> None:
        steps = (
            "      - id: Decide\n        run: echo $GITHUB_EVENT_NAME\n"
            "      - name: Work\n"
            "        if: steps.DECIDE.outputs.skip != 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_RELOCATED]

    def test_an_env_name_in_a_different_case_is_the_same_name(self, tmp_path: Path) -> None:
        findings, _ = lint_one(tmp_path, (ENV_JOB % "echo $event").replace("EVENT:", "Event:"))

        assert kinds(findings) == [KIND_RELOCATED]

    @pytest.mark.parametrize(
        "condition",
        [
            "github.actor_id == '1'",
            "github.event_name_x == 'y'",
            "github.triggering_actor_id == '1'",
        ],
    )
    def test_a_longer_property_name_is_not_the_named_source(
        self, tmp_path: Path, condition: str
    ) -> None:
        steps = f"      - name: Fine\n        if: {condition}\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    def test_an_integer_past_the_digit_limit_does_not_abort_the_scan(
        self, tmp_path: Path
    ) -> None:
        huge = "0x" + "f" * 4000
        steps = (
            f"      - id: big\n        run: echo hi\n        with:\n          n: {huge}\n"
            "      - name: Guarded\n        if: github.actor == 'a'\n        run: echo 1\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_STEP]

    def test_a_value_past_the_node_budget_is_reported_not_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sources, "MAX_NODES", 4)
        steps = (
            "      - id: wide\n        run: echo hi\n        env:\n"
            "          A: 1\n          B: 2\n          C: 3\n          D: 4\n          E: 5\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_UNSCANNED]
        assert "more than 4 nodes" in findings[0].detail

    def test_a_value_past_the_depth_cap_is_reported_not_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sources, "MAX_DEPTH", 2)
        steps = (
            "      - id: deep\n        run: echo hi\n        with:\n"
            "          a:\n            b:\n              c:\n                d: 1\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_UNSCANNED]
        assert "deeper than 2" in findings[0].detail

    def test_text_raises_instead_of_returning_a_partial_answer(self) -> None:
        with pytest.raises(sources.ScanTruncatedError):
            sources.text(list(range(sources.MAX_NODES + 5)))

    def test_text_joins_scalars_from_nested_containers(self) -> None:
        assert sorted(sources.text({"a": ["x", {"b": "y"}], "c": 3}).split("\n")) == [
            "3",
            "x",
            "y",
        ]


class TestThirdReviewFindings:
    """The third security pass: spellings, shell reads, a shared budget, printing."""

    @pytest.mark.parametrize(
        "condition",
        [
            "needs.*.outputs.go == 'true'",
            "contains(toJSON(needs), 'x')",
            "toJSON( NEEDS ) != ''",
        ],
    )
    def test_the_object_filter_and_a_whole_needs_dump_read_other_jobs(
        self, tmp_path: Path, condition: str
    ) -> None:
        steps = f"      - name: Guarded\n        if: {condition}\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_STEP]
        assert "needs.*.outputs" in findings[0].detail

    @pytest.mark.parametrize(
        "condition",
        [
            "contains(toJSON(github), 'push')",
            "github[format('event_{0}', 'name')] == 'push'",
            "github[ inputs.key ] == 'x'",
        ],
    )
    def test_a_github_dump_or_computed_index_reads_the_event_and_actor(
        self, tmp_path: Path, condition: str
    ) -> None:
        steps = f"      - name: Guarded\n        if: {condition}\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_STEP]
        assert "github.event_name" in findings[0].detail
        assert "github.actor" in findings[0].detail

    @pytest.mark.parametrize(
        "condition",
        ["github['ref'] == 'main'", "needs['check'].result == 'success'"],
    )
    def test_a_literal_index_of_another_property_is_not_a_dump(
        self, tmp_path: Path, condition: str
    ) -> None:
        steps = f"      - name: Fine\n        if: {condition}\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert findings == []

    @pytest.mark.parametrize(
        "read",
        [
            "printenv EVENT",
            "python -c \"import os; print(os.environ['EVENT'])\"",
            "python -c \"import os; print(os.environ.get('EVENT'))\"",
            "node -e \"console.log(getenv('EVENT'))\"",
            "echo ${env:EVENT}",
        ],
    )
    def test_more_shell_and_language_env_reads_carry_the_taint(
        self, tmp_path: Path, read: str
    ) -> None:
        findings, _ = lint_one(tmp_path, ENV_JOB % read)

        assert kinds(findings) == [KIND_RELOCATED]

    def test_the_node_budget_is_shared_across_one_jobs_scans(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each value is small; together they exceed the budget."""
        monkeypatch.setattr(sources, "MAX_NODES", 12)
        steps = "".join(
            f"      - id: s{i}\n        run: echo {i}\n        env:\n"
            "          A: 1\n          B: 2\n          C: 3\n"
            for i in range(4)
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_UNSCANNED]

    def test_a_fresh_budget_starts_for_each_producing_job(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sources, "MAX_NODES", 12)
        workflows = tmp_path / "workflows"
        one = "on: push\njobs:\n  {j}:\n    name: {n}\n    steps:\n" + "".join(
            f"      - id: s{i}\n        run: echo {i}\n" for i in range(2)
        )
        write_workflow(workflows, "a.yml", one.format(j="a", n="A"))
        write_workflow(workflows, "b.yml", one.format(j="b", n="B"))

        findings, _ = lint(load_workflows(workflows), ("A", "B"))

        assert findings == []

    def test_a_name_that_cannot_be_encoded_is_escaped_not_raised(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        workflows = tmp_path / "workflows"
        body = (
            "on: pull_request\njobs:\n  gate:\n    name: Run Python Tests\n    steps:\n"
            '      - name: "bad \\uD800 name \\u00e9"\n'
            "        if: github.actor == 'a'\n        run: echo 1\n"
        )
        write_workflow(workflows, "wf.yml", body)

        code = main(["--workflows-dir", str(workflows), "--verbose", "--advisory"])

        out = capsys.readouterr().out
        assert code == 0
        assert out.isascii()
        assert "\\ud800" in out


class TestDevinReviewFindings:
    """Two findings from the automated review of this pull request."""

    def test_a_step_that_overrides_a_tainted_env_with_a_constant_is_not_relocated(
        self, tmp_path: Path
    ) -> None:
        body = """\
            on: pull_request
            jobs:
              gate:
                name: Run Python Tests
                env:
                  EVENT: ${{ github.event_name }}
                steps:
                  - id: decide
                    env:
                      EVENT: fixed
                    run: echo "$EVENT"
                  - name: Work
                    if: steps.decide.outputs.skip != 'true'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert findings == []

    def test_a_step_override_that_itself_reads_a_source_is_still_relocated(
        self, tmp_path: Path
    ) -> None:
        body = """\
            on: pull_request
            jobs:
              gate:
                name: Run Python Tests
                env:
                  EVENT: fixed
                steps:
                  - id: decide
                    env:
                      EVENT: ${{ github.actor }}
                    run: echo "$EVENT"
                  - name: Work
                    if: steps.decide.outputs.skip != 'true'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert kinds(findings) == [KIND_RELOCATED]
        assert "github.actor" in findings[0].detail

    def test_a_step_that_does_not_override_keeps_the_inherited_taint(
        self, tmp_path: Path
    ) -> None:
        body = """\
            on: pull_request
            jobs:
              gate:
                name: Run Python Tests
                env:
                  EVENT: ${{ github.event_name }}
                steps:
                  - id: decide
                    env:
                      OTHER: x
                    run: echo "$EVENT"
                  - name: Work
                    if: steps.decide.outputs.skip != 'true'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert kinds(findings) == [KIND_RELOCATED]

    def test_an_expression_only_job_name_is_reported_not_silently_skipped(
        self, tmp_path: Path
    ) -> None:
        body = "on: push\njobs:\n  a:\n    name: ${{ matrix.x }}\n    steps: []\n"

        findings, producers = lint_one(tmp_path, body, (CONTEXT,))

        assert producers == []
        assert KIND_UNATTRIBUTED in kinds(findings)
        unattributed = next(f for f in findings if f.kind == KIND_UNATTRIBUTED)
        assert unattributed.job == "a"
        assert "any pinned context" in unattributed.detail

    def test_a_partly_literal_expression_name_is_attributed_not_reported(
        self, tmp_path: Path
    ) -> None:
        body = (
            "on: push\njobs:\n  a:\n    name: Run Python Tests (${{ matrix.x }})\n"
            "    steps: []\n"
        )

        findings, _ = lint_one(tmp_path, body, ("Run Python Tests (a)",))

        assert KIND_UNATTRIBUTED not in kinds(findings)

    def test_a_job_whose_body_is_not_a_mapping_is_not_reported(self, tmp_path: Path) -> None:
        findings, _ = lint_one(tmp_path, "on: push\njobs:\n  a: text\n", (CONTEXT,))

        assert KIND_UNATTRIBUTED not in kinds(findings)
