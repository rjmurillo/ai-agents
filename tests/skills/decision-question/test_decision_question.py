"""Tests for the decision-question engine.

Covers every scenario in issue #5408's required-scenarios table plus the
mandated fixtures: over-limit split/prune, delegated-choice no-question,
dependent-decision prune after D1, terminal-task no prompt, and a negative
control proving the capability is load-bearing. Also pins the harness option
bound as UNVERIFIED default four.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "decision-question" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import decision_question as dq


def _decision(**overrides) -> dq.Decision:
    base = dict(
        id="D1",
        statement="Choose the session store.",
        why_now="Blocks the auth skeleton.",
        options=[
            dq.Option(id="redis", label="Redis", consequence="Fast; extra store to run."),
            dq.Option(id="postgres", label="Postgres", consequence="One store; slower check."),
        ],
        recommendation="postgres",
        recommendation_reason="Traffic is under the point where latency matters.",
    )
    base.update(overrides)
    return dq.Decision(**base)


# --- harness bound (pinned, UNVERIFIED) ------------------------------------


def test_harness_bound_default_is_four_and_unverified() -> None:
    assert dq.MAX_PRESENTED_OPTIONS == 4
    assert dq.HARNESS_LIMIT_OBSERVED is False
    assert "no AskUserQuestion" in dq.HARNESS_LIMIT_SOURCE


# --- routing gate ----------------------------------------------------------


def test_route_material_decision_asks() -> None:
    should_ask, reason = dq.route({"material_decision": True})
    assert should_ask is True
    assert "bounded decision brief" in reason


@pytest.mark.parametrize(
    "flag",
    [
        "delegated",
        "policy_mandated",
        "acceptance_criteria_determined",
        "implementation_detail_authorized",
        "resolvable_by_evidence",
        "task_terminal",
    ],
)
def test_route_skip_conditions_win_over_material(flag: str) -> None:
    should_ask, reason = dq.route({"material_decision": True, flag: True})
    assert should_ask is False
    assert reason


def test_route_no_material_decision_skips() -> None:
    should_ask, reason = dq.route({})
    assert should_ask is False
    assert "existing authorization" in reason


def test_route_terminal_takes_precedence_over_delegated() -> None:
    # Ordering: task_terminal is evaluated first and names #5404.
    _, reason = dq.route({"task_terminal": True, "delegated": True})
    assert "#5404" in reason


# --- completeness check ----------------------------------------------------


def test_complete_brief_has_no_missing_fields() -> None:
    assert dq.missing_brief_fields(_decision()) == []
    assert dq.is_complete(_decision()) is True


def test_missing_statement_and_why_now_flagged() -> None:
    missing = dq.missing_brief_fields(_decision(statement="  ", why_now=""))
    assert "statement" in missing
    assert "why_now" in missing


def test_single_option_is_incomplete() -> None:
    d = _decision(options=[dq.Option(id="a", label="A", consequence="x")], recommendation="a")
    assert "at_least_two_options" in dq.missing_brief_fields(d)


def test_cosmetic_options_flagged_not_distinct() -> None:
    d = _decision(
        options=[
            dq.Option(id="a", label="Redis", consequence="x"),
            dq.Option(id="b", label="redis", consequence="y"),
        ],
        recommendation="a",
    )
    assert "options_not_distinct" in dq.missing_brief_fields(d)


def test_option_without_consequence_flagged() -> None:
    d = _decision(
        options=[
            dq.Option(id="redis", label="Redis", consequence=""),
            dq.Option(id="postgres", label="Postgres", consequence="one store"),
        ]
    )
    assert "option[redis].consequence" in dq.missing_brief_fields(d)


def test_missing_recommendation_reason_flagged() -> None:
    assert "recommendation_reason" in dq.missing_brief_fields(_decision(recommendation_reason="  "))


def test_recommendation_unknown_option_flagged() -> None:
    missing = dq.missing_brief_fields(_decision(recommendation="mysql"))
    assert "recommendation_unknown_option" in missing


def test_explicit_no_recommendation_is_complete() -> None:
    d = _decision(no_recommendation=True, recommendation=None, recommendation_reason="")
    assert dq.missing_brief_fields(d) == []


def test_no_recommendation_conflict_flagged() -> None:
    d = _decision(no_recommendation=True)  # keeps recommendation="postgres"
    assert "recommendation_conflicts_with_no_recommendation" in dq.missing_brief_fields(d)


def test_hold_without_reopen_condition_flagged() -> None:
    d = _decision(allow_hold=True, hold_reopen_condition="")
    assert "hold_reopen_condition" in dq.missing_brief_fields(d)


def test_hold_with_reopen_condition_complete() -> None:
    d = _decision(allow_hold=True, hold_reopen_condition="Reopen if p99 exceeds SLO.")
    assert dq.missing_brief_fields(d) == []


# --- option bound: split / prune -------------------------------------------


def test_options_within_bound_single_page_no_sentinel() -> None:
    opts = [dq.Option(id=f"o{i}", label=f"O{i}") for i in range(4)]
    pages = dq.plan_prompt_pages(opts, max_options=4)
    assert len(pages) == 1
    assert [o.id for o in pages[0]] == ["o0", "o1", "o2", "o3"]


def test_six_options_split_deterministically_within_bound() -> None:
    opts = [dq.Option(id=f"o{i}", label=f"O{i}") for i in range(6)]
    pages = dq.plan_prompt_pages(opts, max_options=4)
    assert [[o.id for o in page] for page in pages] == [
        ["o0", "o1", "o2", dq.CONTINUATION_ID],
        ["o3", "o4", "o5"],
    ]
    assert all(len(page) <= 4 for page in pages)


def test_plan_is_stable_across_calls() -> None:
    opts = [dq.Option(id=f"o{i}", label=f"O{i}") for i in range(9)]
    first = [[o.id for o in p] for p in dq.plan_prompt_pages(opts, 4)]
    second = [[o.id for o in p] for p in dq.plan_prompt_pages(opts, 4)]
    assert first == second
    assert all(len(p) <= 4 for p in dq.plan_prompt_pages(opts, 4))


def test_plan_rejects_bound_below_two() -> None:
    with pytest.raises(ValueError):
        dq.plan_prompt_pages([dq.Option(id="a", label="A")], max_options=1)


# --- dependency / split chain ----------------------------------------------


def _chain() -> list[dq.Decision]:
    d1 = dq.Decision(
        id="D1",
        statement="Deploy target?",
        why_now="Shapes every later infra choice.",
        options=[
            dq.Option(id="cloud", label="Cloud", consequence="Managed; ongoing cost."),
            dq.Option(id="onprem", label="On-prem", consequence="Owned; upfront cost."),
        ],
        recommendation="cloud",
        recommendation_reason="No ops team to run on-prem.",
    )
    d2 = dq.Decision(
        id="D2",
        statement="Which managed region?",
        why_now="Only relevant once cloud is chosen.",
        options=[
            dq.Option(id="us", label="US", consequence="Lowest latency for US users."),
            dq.Option(id="eu", label="EU", consequence="Data residency in EU."),
        ],
        recommendation="us",
        recommendation_reason="Most users are in the US.",
        requires={"D1": "cloud"},
    )
    return [d1, d2]


def test_next_decision_asks_earliest_first() -> None:
    assert dq.next_decision(_chain(), answers={}).id == "D1"


def test_dependent_decision_pruned_when_prerequisite_unmet() -> None:
    kept = dq.prune_chain(_chain(), answers={"D1": "onprem"})
    assert [d.id for d in kept] == ["D1"]
    assert dq.next_decision(_chain(), answers={"D1": "onprem"}) is None


def test_dependent_decision_recomputed_when_prerequisite_met() -> None:
    assert dq.next_decision(_chain(), answers={"D1": "cloud"}).id == "D2"


def test_option_level_requires_filters_dead_options() -> None:
    d = dq.Decision(
        id="D2",
        statement="Region?",
        why_now="x",
        options=[
            dq.Option(id="us", label="US", consequence="a"),
            dq.Option(id="eu", label="EU", consequence="b", requires={"D1": "onprem"}),
        ],
    )
    kept = dq.prune_chain([d], answers={"D1": "cloud"})
    assert [o.id for o in kept[0].options] == ["us"]


def test_ids_preserved_not_renumbered_after_prune() -> None:
    kept = dq.prune_chain(_chain(), answers={"D1": "cloud"})
    assert [d.id for d in kept] == ["D1", "D2"]


# --- negative control: capability is load-bearing --------------------------


def test_negative_control_without_bounding_request_overflows() -> None:
    # Six raw options exceed the harness bound: a naive request that skips
    # plan_prompt_pages would present all six in one prompt.
    raw = [dq.Option(id=f"o{i}", label=f"O{i}") for i in range(6)]
    assert len(raw) > dq.MAX_PRESENTED_OPTIONS  # the vague/over-limit request
    pages = dq.plan_prompt_pages(raw, dq.MAX_PRESENTED_OPTIONS)
    # With the capability, every page is within bound and all options survive.
    assert all(len(p) <= dq.MAX_PRESENTED_OPTIONS for p in pages)
    presented = {o.id for p in pages for o in p if o.id != dq.CONTINUATION_ID}
    assert presented == {o.id for o in raw}


def test_negative_control_without_completeness_check_ships_vague_brief() -> None:
    # A brief with no "why now" and a bare option is what an agent would emit
    # without the completeness gate; the capability catches it.
    vague = dq.Decision(
        id="D1",
        statement="Pick one.",
        why_now="",
        options=[dq.Option(id="a", label="A", consequence="")],
    )
    assert dq.missing_brief_fields(vague)  # capability blocks it
    assert dq.missing_brief_fields(_decision()) == []  # enriched brief passes


# --- evaluate() end to end -------------------------------------------------


def test_evaluate_delegated_skips() -> None:
    data = {"context": {"material_decision": True, "delegated": True}, "decisions": []}
    result = dq.evaluate(data)
    assert result["status"] == "skip"
    assert result["should_ask"] is False


def test_evaluate_terminal_task_skips() -> None:
    data = {"context": {"material_decision": True, "task_terminal": True}, "decisions": []}
    result = dq.evaluate(data)
    assert result["status"] == "skip"
    assert "#5404" in result["reason"]


def test_evaluate_material_complete_asks() -> None:
    data = {
        "context": {"material_decision": True},
        "decisions": [json.loads(_to_json(_decision()))],
    }
    result = dq.evaluate(data)
    assert result["status"] == "ask"
    assert result["decision_id"] == "D1"
    assert result["split"] is False


def test_evaluate_incomplete_reports_missing() -> None:
    data = {
        "context": {"material_decision": True},
        "decisions": [{"id": "D1", "statement": "Pick.", "why_now": "", "options": []}],
    }
    result = dq.evaluate(data)
    assert result["status"] == "incomplete"
    assert "why_now" in result["missing"]


def test_evaluate_over_limit_reports_split() -> None:
    opts = [{"id": f"o{i}", "label": f"O{i}", "consequence": f"c{i}"} for i in range(6)]
    data = {
        "context": {"material_decision": True},
        "decisions": [
            {
                "id": "D1",
                "statement": "Pick a runtime.",
                "why_now": "Blocks the build.",
                "options": opts,
                "no_recommendation": True,
            }
        ],
    }
    result = dq.evaluate(data)
    assert result["status"] == "ask"
    assert result["split"] is True
    assert all(len(page) <= dq.MAX_PRESENTED_OPTIONS for page in result["pages"])


# --- CLI exit codes (documented contract) ----------------------------------


def _to_json(decision: dq.Decision) -> str:
    return json.dumps(
        {
            "id": decision.id,
            "statement": decision.statement,
            "why_now": decision.why_now,
            "options": [
                {"id": o.id, "label": o.label, "consequence": o.consequence}
                for o in decision.options
            ],
            "recommendation": decision.recommendation,
            "recommendation_reason": decision.recommendation_reason,
        }
    )


def test_cli_exit_zero_on_complete_brief(tmp_path: Path, capsys) -> None:
    brief = tmp_path / "brief.json"
    decisions = [json.loads(_to_json(_decision()))]
    payload = {"context": {"material_decision": True}, "decisions": decisions}
    brief.write_text(json.dumps(payload), encoding="utf-8")
    assert dq.main(["--brief", str(brief)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ask"


def test_cli_exit_zero_on_skip(tmp_path: Path) -> None:
    brief = tmp_path / "brief.json"
    payload = {"context": {"delegated": True}, "decisions": []}
    brief.write_text(json.dumps(payload), encoding="utf-8")
    assert dq.main(["--brief", str(brief)]) == 0


def test_cli_exit_two_on_incomplete(tmp_path: Path) -> None:
    brief = tmp_path / "brief.json"
    brief.write_text(
        json.dumps(
            {
                "context": {"material_decision": True},
                "decisions": [{"id": "D1", "statement": "Pick.", "why_now": "", "options": []}],
            }
        ),
        encoding="utf-8",
    )
    assert dq.main(["--brief", str(brief)]) == 2


def test_cli_exit_one_on_missing_file(tmp_path: Path) -> None:
    assert dq.main(["--brief", str(tmp_path / "nope.json")]) == 1


def test_cli_exit_one_on_malformed_json(tmp_path: Path) -> None:
    brief = tmp_path / "brief.json"
    brief.write_text("not json", encoding="utf-8")
    assert dq.main(["--brief", str(brief)]) == 1


def test_cli_max_options_override(tmp_path: Path, capsys) -> None:
    opts = [{"id": f"o{i}", "label": f"O{i}", "consequence": f"c{i}"} for i in range(3)]
    brief = tmp_path / "brief.json"
    brief.write_text(
        json.dumps(
            {
                "context": {"material_decision": True},
                "decisions": [
                    {
                        "id": "D1",
                        "statement": "Pick.",
                        "why_now": "now",
                        "options": opts,
                        "no_recommendation": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert dq.main(["--brief", str(brief), "--max-options", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["split"] is True
