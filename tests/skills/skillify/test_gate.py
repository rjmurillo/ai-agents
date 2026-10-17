"""step 2 gate: reject one-off and trivial work, proceed on real procedure."""

from __future__ import annotations

import pytest
import skillify


def audit(**overrides):
    base = {
        "tool_call_count": 7,
        "reusable_class": True,
        "decision_points": 2,
        "gotchas": ["path with spaces"],
        "trigger_phrase": "ingest a meeting transcript",
    }
    base.update(overrides)
    return base


def codes(result):
    return [reason["code"] for reason in result["reasons"]]


def test_proceeds_on_reusable_multi_step_work():
    result = skillify.evaluate_gate(audit())
    assert result["status"] == "PROCEED"
    assert result["reasons"] == []


def test_rejects_one_off_work():
    result = skillify.evaluate_gate(audit(reusable_class=False))
    assert result["status"] == "REJECT"
    assert codes(result) == ["one_off"]


def test_rejects_single_tool_call_wrapper():
    result = skillify.evaluate_gate(audit(tool_call_count=1))
    assert result["status"] == "REJECT"
    assert codes(result) == ["trivial_wrapper"]


def test_rejects_zero_tool_calls():
    assert codes(skillify.evaluate_gate(audit(tool_call_count=0))) == ["trivial_wrapper"]


def test_two_tool_calls_is_the_floor():
    assert skillify.evaluate_gate(audit(tool_call_count=2))["status"] == "PROCEED"


def test_rejects_work_without_decision_or_gotcha():
    result = skillify.evaluate_gate(audit(decision_points=0, gotchas=[]))
    assert codes(result) == ["no_real_procedure"]


def test_one_gotcha_alone_is_enough_procedure():
    assert skillify.evaluate_gate(audit(decision_points=0, gotchas=1))["status"] == "PROCEED"


def test_one_decision_alone_is_enough_procedure():
    assert skillify.evaluate_gate(audit(decision_points=1, gotchas=0))["status"] == "PROCEED"


@pytest.mark.parametrize("phrase", ["", "   ", "\t\n"])
def test_rejects_blank_trigger_phrase(phrase):
    assert codes(skillify.evaluate_gate(audit(trigger_phrase=phrase))) == ["no_trigger_phrase"]


def test_reports_every_failed_rule():
    result = skillify.evaluate_gate(
        audit(
            reusable_class=False,
            tool_call_count=1,
            decision_points=0,
            gotchas=0,
            trigger_phrase="",
        )
    )
    assert codes(result) == [
        "one_off",
        "trivial_wrapper",
        "no_real_procedure",
        "no_trigger_phrase",
    ]


def test_external_actions_flag_requires_approval_gate():
    assert skillify.evaluate_gate(audit(external_actions=True))["approval_gate_required"] is True
    assert skillify.evaluate_gate(audit())["approval_gate_required"] is False


@pytest.mark.parametrize("field", ["external_actions", "recovery_paths"])
@pytest.mark.parametrize("bad", ["yes", 1, 0, None, []])
def test_optional_flags_must_be_strict_bool(field, bad):
    with pytest.raises(skillify.SkillifyError, match=field):
        skillify.evaluate_gate(audit(**{field: bad}))


def test_recovery_paths_flag_is_reported():
    assert skillify.evaluate_gate(audit(recovery_paths=True))["recovery_paths_required"] is True
    assert skillify.evaluate_gate(audit())["recovery_paths_required"] is False


def test_proactive_eligibility_needs_five_calls_and_proceed():
    assert skillify.evaluate_gate(audit(tool_call_count=5))["proactive_eligible"] is True
    assert skillify.evaluate_gate(audit(tool_call_count=4))["proactive_eligible"] is False
    rejected = skillify.evaluate_gate(audit(tool_call_count=9, reusable_class=False))
    assert rejected["proactive_eligible"] is False


@pytest.mark.parametrize(
    "bad",
    [
        [],
        "text",
        None,
        audit(tool_call_count=True),
        audit(tool_call_count=-1),
        audit(tool_call_count="7"),
        audit(reusable_class="yes"),
        audit(decision_points="two"),
        audit(gotchas=None),
        audit(trigger_phrase=5),
    ],
)
def test_malformed_audit_raises(bad):
    with pytest.raises(skillify.SkillifyError):
        skillify.evaluate_gate(bad)


def test_missing_fields_are_named():
    with pytest.raises(skillify.SkillifyError, match="gotchas"):
        skillify.evaluate_gate({"tool_call_count": 3})
