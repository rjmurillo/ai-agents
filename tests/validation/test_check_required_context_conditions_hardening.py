"""Hardening cases for check_required_context_conditions.py.

Spellings and inputs a security review found could evade or crash the lint. The
core analysis cases live in test_check_required_context_conditions.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import pytest
from check_required_context_conditions import (
    KIND_RELOCATED,
    KIND_STEP,
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


class TestHardening:
    """Spellings and inputs a reviewer found could evade or crash the lint."""

    @pytest.mark.parametrize(
        "condition",
        [
            "github.Actor == 'a'",
            "GITHUB.EVENT_NAME == 'push'",
            "NEEDS.check.OUTPUTS.go == 'true'",
            "github.triggering_actor == 'a'",
            "github['triggering_actor'] == 'a'",
        ],
    )
    def test_case_and_triggering_actor_spellings_are_flagged(
        self, tmp_path: Path, condition: str
    ) -> None:
        steps = f"      - name: Guarded\n        if: {condition}\n        run: echo hi\n"

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_STEP]

    def test_bracket_spelling_of_step_outputs_is_followed(self, tmp_path: Path) -> None:
        steps = (
            "      - id: g\n        run: echo $GITHUB_EVENT_NAME\n"
            "      - name: Work\n"
            "        if: steps['g'].outputs.skip != 'true'\n"
            "        run: pytest\n"
        )

        findings, _ = lint_one(tmp_path, job_body(steps=steps))

        assert kinds(findings) == [KIND_RELOCATED]

    def test_a_job_level_env_that_carries_the_event_name_taints_a_step_read(
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
                  - name: Work
                    if: env.EVENT != 'merge_group'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert kinds(findings) == [KIND_RELOCATED]
        assert "github.event_name" in findings[0].detail

    def test_a_workflow_level_env_taints_a_step_that_feeds_a_later_condition(
        self, tmp_path: Path
    ) -> None:
        body = """\
            on: pull_request
            env:
              WHO: ${{ github.actor }}
            jobs:
              gate:
                name: Run Python Tests
                steps:
                  - id: decide
                    run: echo "actor is ${{ env.WHO }}"
                  - name: Work
                    if: steps.decide.outputs.skip != 'true'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert kinds(findings) == [KIND_RELOCATED]
        assert "github.actor" in findings[0].detail

    def test_a_job_level_env_overrides_a_tainted_workflow_level_one(
        self, tmp_path: Path
    ) -> None:
        body = """\
            on: pull_request
            env:
              MODE: ${{ github.event_name }}
            jobs:
              gate:
                name: Run Python Tests
                env:
                  MODE: fixed
                steps:
                  - name: Work
                    if: env.MODE == 'fixed'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert findings == []

    def test_an_untainted_env_read_is_not_flagged(self, tmp_path: Path) -> None:
        body = """\
            on: pull_request
            env:
              MODE: strict
            jobs:
              gate:
                name: Run Python Tests
                steps:
                  - name: Work
                    if: env.MODE == 'strict'
                    run: pytest
            """

        findings, _ = lint_one(tmp_path, body)

        assert findings == []

    def test_an_expression_only_job_name_claims_no_pinned_context(
        self, tmp_path: Path
    ) -> None:
        body = "on: push\njobs:\n  a:\n    name: ${{ matrix.x }}\n    steps: []\n"
        documents = load_workflows(_dir(tmp_path, body))

        assert producing_jobs(documents, (CONTEXT, "Other")) == []

    def test_an_aliased_bomb_is_read_in_bounded_time(self, tmp_path: Path) -> None:
        """Nested aliases stay small in memory but `str()` of them does not."""
        levels = ["a: &a [x, x, x, x, x, x, x, x, x, x]"]
        for name, prev in zip("bcdefghijk", "abcdefghij", strict=True):
            levels.append(f"{name}: &{name} [*{prev}, *{prev}, *{prev}, *{prev}, *{prev}, "
                          f"*{prev}, *{prev}, *{prev}, *{prev}, *{prev}]")
        anchors = "\n".join(f"          {line}" for line in levels)
        body = (
            "on: pull_request\njobs:\n  gate:\n    name: Run Python Tests\n"
            "    steps:\n      - name: Bomb\n        id: bomb\n        run: echo hi\n"
            "        with:\n"
            + anchors
            + "\n        if: github.actor == 'a'\n"
        )

        findings, _ = lint_one(tmp_path, body)

        assert kinds(findings) == [KIND_STEP]


def _dir(tmp_path: Path, body: str) -> Path:
    workflows = tmp_path / "workflows"
    write_workflow(workflows, "wf.yml", body)
    return workflows
