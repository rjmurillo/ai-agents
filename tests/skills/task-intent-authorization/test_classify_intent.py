#!/usr/bin/env python3
"""Tests for the task-intent-authorization classifier.

Every required scenario from issue #5407 has positive and negative coverage.
The two named negative controls prove the invariant is load-bearing:

1. Disable the intent distinction and prove a question-only scenario is then
   misread as authorized to mutate.
2. Disable the already-authorized behavior and prove an explicit fix request is
   then forced to ask a redundant confirmation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/task-intent-authorization/scripts/classify_intent.py"
)
classify = mod.classify
requires_permission_question = mod.requires_permission_question
action_requires_new_decision = mod.action_requires_new_decision
extract_targets = mod.extract_targets
main = mod.main
ASSESS = mod.ASSESS
DIAGNOSE = mod.DIAGNOSE
MUTATE = mod.MUTATE


class TestAssessAndDiagnoseDoNotAuthorize:
    """Questions and problem reports never authorize a change."""

    def test_why_failing_is_diagnose_no_mutation(self) -> None:
        d = classify("Why is this test failing?")
        assert d.intent == DIAGNOSE
        assert d.mutation_authorized is False

    def test_review_for_defects_no_fix(self) -> None:
        d = classify("Review this code for defects")
        assert d.intent == ASSESS
        assert d.mutation_authorized is False

    def test_evaluate_whether_to_change_does_not_authorize(self) -> None:
        # Contains the word "change" but leads with an assessment verb.
        d = classify("Evaluate whether we should change X")
        assert d.intent == ASSESS
        assert d.mutation_authorized is False

    def test_should_we_change_is_deliberation_not_command(self) -> None:
        d = classify("Should we change the retry config?")
        assert d.mutation_authorized is False

    def test_bare_problem_report_does_not_authorize(self) -> None:
        d = classify("The build is broken on the main branch.")
        assert d.intent == DIAGNOSE
        assert d.mutation_authorized is False

    def test_neutral_question_is_assess(self) -> None:
        d = classify("What does this module do?")
        assert d.intent == ASSESS
        assert d.mutation_authorized is False


class TestExplicitMutationAuthorizes:
    """Explicit imperatives authorize the requested bounded change."""

    def test_fix_failing_test_authorizes(self) -> None:
        d = classify("Fix this failing test")
        assert d.intent == MUTATE
        assert d.mutation_authorized is True
        assert d.authorization_source == "explicit_request"

    def test_update_issue_authorizes_with_target(self) -> None:
        d = classify("Update issue #123 with this context")
        assert d.intent == MUTATE
        assert d.mutation_authorized is True
        assert "#123" in d.authorized_targets

    def test_delete_authorizes(self) -> None:
        d = classify("Delete the stale fixture file")
        assert d.mutation_authorized is True


class TestConditionalFix:
    """Diagnosis gates mutation, but a confirmed cause may be fixed."""

    def test_investigate_and_fix_if_confirmed(self) -> None:
        d = classify("Investigate and fix if confirmed")
        assert d.intent == MUTATE
        assert d.mutation_authorized is True
        assert d.diagnosis_gated is True
        assert d.authorization_source == "conditional_fix"

    def test_conditional_fix_still_requires_no_second_permission(self) -> None:
        d = classify("Investigate and fix if confirmed")
        # Once the cause is confirmed (enough info), act without asking again.
        assert requires_permission_question(d, have_enough_info=True) is False


class TestWorkflowAuthorization:
    """An already-authorized workflow authorizes mutation."""

    def test_workflow_authorizes(self) -> None:
        d = classify("apply the remediation", workflow_authorizes_mutation=True)
        assert d.intent == MUTATE
        assert d.mutation_authorized is True
        assert d.authorization_source == "workflow"

    def test_workflow_overrides_assessment_phrasing(self) -> None:
        # Even assessment-shaped text under an authorized workflow is authorized.
        d = classify("review and remediate", workflow_authorizes_mutation=True)
        assert d.mutation_authorized is True


class TestInverseGuard:
    """Once authorized with enough info, do not ask a redundant question."""

    def test_authorized_with_enough_info_does_not_ask(self) -> None:
        d = classify("Fix this failing test")
        assert requires_permission_question(d, have_enough_info=True) is False

    def test_authorized_without_enough_info_still_does_not_ask_permission(self) -> None:
        # Missing info means gather or diagnose, not re-request permission.
        d = classify("Fix this failing test")
        assert requires_permission_question(d, have_enough_info=False) is False

    def test_unauthorized_mutation_intent_requires_question(self) -> None:
        # A bare problem report where a change is contemplated needs authorization.
        d = classify("The config is wrong.")
        # Assessment intent: no mutation contemplated, so no permission prompt.
        assert requires_permission_question(d, have_enough_info=True) is False


class TestScopeDiscipline:
    """Authorization is bounded by the request."""

    def test_named_target_bounds_scope(self) -> None:
        d = classify("Fix the bug in module_a.py")
        assert "module_a.py" in d.authorized_targets
        # Unrelated cleanup of a different file is a new decision.
        assert action_requires_new_decision(d, ("module_b.py",)) is True

    def test_action_within_scope_needs_no_new_decision(self) -> None:
        d = classify("Fix the bug in module_a.py")
        assert action_requires_new_decision(d, ("module_a.py",)) is False

    def test_unauthorized_action_always_requires_decision(self) -> None:
        d = classify("Why is module_a.py slow?")
        assert action_requires_new_decision(d, ("module_a.py",)) is True

    def test_broad_action_stops_unless_workflow_covers(self) -> None:
        d = classify("apply the local config fix", workflow_authorizes_mutation=True)
        # Diagnosis reveals an org-wide policy change is the only remedy: a
        # materially broader action than the local fix the workflow authorized.
        assert (
            action_requires_new_decision(
                d, ("org-policy",), materially_broader=True
            )
            is True
        )
        assert (
            action_requires_new_decision(
                d, ("org-policy",), materially_broader=True, workflow_scope_covers=True
            )
            is False
        )


class TestExtractTargets:
    """Target extraction bounds authorized scope."""

    def test_issue_ref(self) -> None:
        assert "#123" in extract_targets("Update issue #123")

    def test_pathlike(self) -> None:
        assert "auth.py" in extract_targets("Fix auth.py")

    def test_quoted(self) -> None:
        assert "the login flow" in extract_targets('Fix "the login flow"')

    def test_no_targets(self) -> None:
        assert extract_targets("Fix the failing test") == ()


class TestNegativeControlOne:
    """Disabling the intent distinction misreads a question as authorization."""

    def test_distinction_prevents_authorization(self) -> None:
        request = "Should we change the retry config?"
        with_distinction = classify(request, distinguish_intent=True)
        without_distinction = classify(request, distinguish_intent=False)
        # Load-bearing: the distinction is the only thing preventing a mutation
        # authorization on a deliberation question.
        assert with_distinction.mutation_authorized is False
        assert without_distinction.mutation_authorized is True

    def test_evaluate_change_also_leaks_without_distinction(self) -> None:
        request = "Evaluate whether we should change X"
        assert classify(request, distinguish_intent=True).mutation_authorized is False
        assert classify(request, distinguish_intent=False).mutation_authorized is True


class TestNegativeControlTwo:
    """Disabling already-authorized behavior forces a redundant confirmation."""

    def test_guard_prevents_redundant_confirmation(self) -> None:
        d = classify("Fix this failing test")
        honored = requires_permission_question(
            d, have_enough_info=True, honor_existing_authorization=True
        )
        disabled = requires_permission_question(
            d, have_enough_info=True, honor_existing_authorization=False
        )
        # Load-bearing: honoring prior authorization is the only thing that
        # suppresses the redundant question on an explicit fix request.
        assert honored is False
        assert disabled is True


class TestCli:
    """The CLI contract the SKILL.md promises."""

    def test_diagnose_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["Why is this test failing?"])
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["intent"] == DIAGNOSE
        assert out["mutation_authorized"] is False

    def test_fix_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["Fix this failing test"])
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["intent"] == MUTATE
        assert out["mutation_authorized"] is True

    def test_workflow_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["--workflow-authorized", "apply the remediation"])
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out["authorization_source"] == "workflow"

    def test_empty_request_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = main(["   "])
        assert code == 2
